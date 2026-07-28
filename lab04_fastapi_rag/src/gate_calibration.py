from __future__ import annotations

import os
import shutil
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Sequence

from .embedding_config import EmbeddingConfig
from .embedding_model import (
    TransformerEmbeddingBackend,
    installed_dependency_versions,
    normalize_query,
    validate_embedding_matrix,
    verify_required_model_files,
)
from .h2_questions import H2Question, load_gate_policy, load_h2_question_set
from .index_builder import _local_snapshot
from .io_utils import (
    read_json,
    sha256_file,
    write_json_atomic,
    write_text_atomic,
)
from .paths import (
    CALIBRATION_QUESTIONS_PATH,
    EVALUATION_QUESTIONS_PATH,
    H2_FREEZE_PATH,
    PROJECT_ROOT,
    RETRIEVAL_GATE_POLICY_PATH,
)
from .retriever import load_validated_index


class GateCalibrationError(RuntimeError):
    """Raised when a frozen H2 gate cannot be calibrated reproducibly."""


@dataclass(frozen=True)
class ThresholdMetrics:
    threshold: float
    true_positive: int
    false_negative: int
    true_negative: int
    false_positive: int
    in_scope_recall: float
    negative_rejection_rate: float
    balanced_accuracy: float
    recall_constraint_met: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "threshold": self.threshold,
            "true_positive": self.true_positive,
            "false_negative": self.false_negative,
            "true_negative": self.true_negative,
            "false_positive": self.false_positive,
            "in_scope_recall": self.in_scope_recall,
            "negative_rejection_rate": self.negative_rejection_rate,
            "balanced_accuracy": self.balanced_accuracy,
            "recall_constraint_met": self.recall_constraint_met,
        }


def _require_mapping(payload: Any, name: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise GateCalibrationError(f"{name}必须是JSON对象")
    return payload


def _resolve_frozen_path(relative_path: Any, expected: Path) -> Path:
    text = str(relative_path)
    path = (PROJECT_ROOT / text).resolve()
    if path != expected.resolve():
        raise GateCalibrationError(f"H2冻结路径不匹配：{text}")
    return path


def validate_h2_freeze(
    *,
    freeze_path: Path = H2_FREEZE_PATH,
    calibration_path: Path = CALIBRATION_QUESTIONS_PATH,
    evaluation_path: Path = EVALUATION_QUESTIONS_PATH,
    gate_policy_path: Path = RETRIEVAL_GATE_POLICY_PATH,
) -> dict[str, Any]:
    """Validate H2 bytes without deserializing the sealed evaluation set."""
    freeze = _require_mapping(read_json(freeze_path), "h2_freeze")
    if freeze.get("schema_version") != "h2_freeze_v1":
        raise GateCalibrationError("不支持的H2冻结清单版本")
    if freeze.get("status") != "h2_frozen_user_confirmed":
        raise GateCalibrationError("H2尚未由用户确认冻结")

    calibration = _require_mapping(
        freeze.get("calibration_set"),
        "calibration_set",
    )
    evaluation = _require_mapping(
        freeze.get("evaluation_set"),
        "evaluation_set",
    )
    gate_policy = _require_mapping(freeze.get("gate_policy"), "gate_policy")
    controls = _require_mapping(
        freeze.get("leakage_controls"),
        "leakage_controls",
    )
    checks = (
        (
            _resolve_frozen_path(calibration.get("path"), calibration_path),
            calibration.get("sha256"),
            "校准集",
        ),
        (
            _resolve_frozen_path(evaluation.get("path"), evaluation_path),
            evaluation.get("sha256"),
            "正式集",
        ),
        (
            _resolve_frozen_path(gate_policy.get("path"), gate_policy_path),
            gate_policy.get("sha256"),
            "门控策略",
        ),
    )
    for path, expected_hash, label in checks:
        if not path.is_file():
            raise FileNotFoundError(f"{label}文件不存在：{path.name}")
        if sha256_file(path) != expected_hash:
            raise GateCalibrationError(f"{label}SHA-256与H2冻结清单不一致")

    if gate_policy.get("algorithm_confirmed") is not True:
        raise GateCalibrationError("门控算法尚未确认")
    if controls != {
        "evaluation_file_hash_only_before_threshold_freeze": True,
        "evaluation_retrieval_before_threshold_freeze": False,
        "retune_after_evaluation": False,
    }:
        raise GateCalibrationError("H2数据隔离规则与冻结方案不一致")
    return freeze


def candidate_thresholds(scores: Sequence[float]) -> list[float]:
    import numpy as np

    values = np.asarray(scores, dtype=np.float64)
    if values.ndim != 1 or values.size == 0:
        raise ValueError("校准分数必须是一维非空数组")
    if not np.isfinite(values).all():
        raise ValueError("校准分数包含NaN或Infinity")
    unique = np.unique(values)
    thresholds = [float(np.nextafter(unique[0], -np.inf))]
    thresholds.extend(
        float(left + (right - left) / 2.0)
        for left, right in zip(unique[:-1], unique[1:])
    )
    thresholds.append(float(np.nextafter(unique[-1], np.inf)))
    return thresholds


def evaluate_threshold(
    scores: Sequence[float],
    scopes: Sequence[str],
    threshold: float,
    minimum_in_scope_recall: float,
) -> ThresholdMetrics:
    if len(scores) != len(scopes) or not scores:
        raise ValueError("分数与标签必须等长且非空")
    positives = sum(scope == "in_scope" for scope in scopes)
    negatives = len(scopes) - positives
    if positives == 0 or negatives == 0:
        raise ValueError("校准集必须同时包含库内题和负样本")
    true_positive = false_negative = true_negative = false_positive = 0
    for score, scope in zip(scores, scopes):
        predicted_pass = score >= threshold
        if scope == "in_scope":
            true_positive += int(predicted_pass)
            false_negative += int(not predicted_pass)
        else:
            true_negative += int(not predicted_pass)
            false_positive += int(predicted_pass)
    recall = true_positive / positives
    rejection = true_negative / negatives
    return ThresholdMetrics(
        threshold=float(threshold),
        true_positive=true_positive,
        false_negative=false_negative,
        true_negative=true_negative,
        false_positive=false_positive,
        in_scope_recall=recall,
        negative_rejection_rate=rejection,
        balanced_accuracy=(recall + rejection) / 2.0,
        recall_constraint_met=recall >= minimum_in_scope_recall,
    )


def select_threshold(
    scores: Sequence[float],
    scopes: Sequence[str],
    minimum_in_scope_recall: float,
) -> tuple[ThresholdMetrics, list[ThresholdMetrics], str]:
    metrics = [
        evaluate_threshold(
            scores,
            scopes,
            threshold,
            minimum_in_scope_recall,
        )
        for threshold in candidate_thresholds(scores)
    ]
    feasible = [item for item in metrics if item.recall_constraint_met]
    if feasible:
        selected = max(
            feasible,
            key=lambda item: (
                item.negative_rejection_rate,
                item.balanced_accuracy,
                item.in_scope_recall,
                item.threshold,
            ),
        )
        reason = (
            "满足库内召回率不低于0.9；先最大化负样本拒绝率，"
            "再按平衡准确率、库内召回率和较高阈值依次破同分。"
        )
    else:
        selected = max(
            metrics,
            key=lambda item: (
                item.balanced_accuracy,
                item.in_scope_recall,
                item.negative_rejection_rate,
                -item.threshold,
            ),
        )
        reason = (
            "没有候选阈值满足最低库内召回率；按冻结回退规则依次最大化"
            "平衡准确率、库内召回率、负样本拒绝率并选择较低阈值。"
        )
    return selected, metrics, reason


def _top1_records(
    questions: Sequence[H2Question],
    query_matrix: Any,
    index_matrix: Any,
    chunks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    import numpy as np

    score_matrix = query_matrix @ index_matrix.T
    if not np.isfinite(score_matrix).all():
        raise GateCalibrationError("校准相似度包含NaN或Infinity")
    records: list[dict[str, Any]] = []
    for row, question in enumerate(questions):
        top_index = int(np.argmax(score_matrix[row]))
        chunk = chunks[top_index]
        records.append(
            {
                "question_id": question.question_id,
                "scope": question.scope,
                "question": question.question,
                "expected_gate_decision": (
                    "pass" if question.scope == "in_scope" else "reject"
                ),
                "top1_score": float(score_matrix[row, top_index]),
                "top1": {
                    "row_index": top_index,
                    "chunk_id": chunk["chunk_id"],
                    "page_title": chunk["page_title"],
                    "section_path": chunk["section_path"],
                    "source_path": chunk["source_path"],
                    "content_sha256": chunk["content_sha256"],
                },
            }
        )
    return records


def _render_report(
    summary: dict[str, Any],
    records: Sequence[dict[str, Any]],
) -> str:
    selected = summary["selected_metrics"]
    false_rejects = [
        item
        for item in records
        if item["expected_gate_decision"] == "pass"
        and item["gate_decision"] == "reject"
    ]
    false_accepts = [
        item
        for item in records
        if item["expected_gate_decision"] == "reject"
        and item["gate_decision"] == "pass"
    ]
    lines = [
        "# H3检索门控阈值校准报告",
        "",
        f"- 状态：{summary['status']}",
        f"- 实验运行：`{summary['experiment_run_id']}`",
        f"- 校准题：{summary['calibration_question_count']}",
        "- 正式题读取：否（仅核验文件SHA-256）",
        "- 在线生成模型调用：否",
        f"- 正式阈值候选：`{summary['selected_threshold']!r}`",
        f"- 库内召回率：{selected['in_scope_recall']:.4f}",
        f"- 负样本拒绝率：{selected['negative_rejection_rate']:.4f}",
        f"- 平衡准确率：{selected['balanced_accuracy']:.4f}",
        (
            "- 混淆计数："
            f"TP={selected['true_positive']}，"
            f"FN={selected['false_negative']}，"
            f"TN={selected['true_negative']}，"
            f"FP={selected['false_positive']}"
        ),
        f"- 选择理由：{summary['selection_reason']}",
        "",
        "## 错误门控样本",
        "",
        f"### 错误拒绝（{len(false_rejects)}）",
        "",
    ]
    lines.extend(
        (
            f"- `{item['question_id']}` score={item['top1_score']!r}；"
            f"{item['top1']['source_path']}"
        )
        for item in false_rejects
    )
    if not false_rejects:
        lines.append("- 无")
    lines.extend(["", f"### 错误放行（{len(false_accepts)}）", ""])
    lines.extend(
        (
            f"- `{item['question_id']}` score={item['top1_score']!r}；"
            f"{item['top1']['source_path']}"
        )
        for item in false_accepts
    )
    if not false_accepts:
        lines.append("- 无")
    lines.extend(
        [
            "",
            "## 数据隔离",
            "",
            "- 校准前核验了校准集、正式集和门控策略三个冻结哈希。",
            "- 本次只反序列化并编码50道校准题。",
            "- 30道正式题未反序列化、未编码、未检索、未产生分数。",
            "- 本报告尚待用户确认；确认前不运行正式题和在线生成模型。",
            "",
        ]
    )
    return "\n".join(lines)


def _record_failure(run_dir: Path, error: Exception) -> Path:
    directory = run_dir / "calibration" / "failures"
    directory.mkdir(parents=True, exist_ok=True)
    existing = sorted(directory.glob("failure_*.json"))
    path = directory / f"failure_{len(existing) + 1:03d}.json"
    message = str(error)
    for sensitive in (Path.home(), PROJECT_ROOT):
        message = message.replace(str(sensitive), "<LOCAL_PATH>")
    write_json_atomic(
        path,
        {
            "schema_version": "gate_calibration_failure_v1",
            "experiment_run_id": run_dir.name,
            "failed_at": datetime.now().astimezone().isoformat(),
            "error_type": type(error).__name__,
            "error_message": message,
            "online_model_called": False,
            "evaluation_retrieval_called": False,
        },
    )
    return path


def calibrate_gate(
    run_dir: Path,
    config: EmbeddingConfig,
    frozen_device: str,
    *,
    snapshot_locator: Callable[[EmbeddingConfig], Path] = _local_snapshot,
    backend_factory: Callable[
        [Path, EmbeddingConfig, str],
        TransformerEmbeddingBackend,
    ] = TransformerEmbeddingBackend,
) -> dict[str, Any]:
    output_dir = run_dir / "calibration" / "threshold_v1"
    if output_dir.exists():
        raise FileExistsError("calibration/threshold_v1已存在，拒绝覆盖")
    staging_dir: Path | None = None
    backend = None
    try:
        started = time.perf_counter()
        freeze = validate_h2_freeze()
        policy = load_gate_policy(RETRIEVAL_GATE_POLICY_PATH)
        calibration = load_h2_question_set(CALIBRATION_QUESTIONS_PATH)
        if calibration.set_role != "calibration":
            raise GateCalibrationError("冻结校准文件的set_role不是calibration")
        if calibration.set_id != freeze["calibration_set"]["set_id"]:
            raise GateCalibrationError("校准集ID与H2冻结清单不一致")
        if len(calibration.questions) != 50:
            raise GateCalibrationError("冻结校准集必须包含50道题")
        if policy.get("calibration_set_id") != calibration.set_id:
            raise GateCalibrationError("门控策略引用了不同的校准集")
        if policy.get("evaluation_set_id") != freeze["evaluation_set"]["set_id"]:
            raise GateCalibrationError("门控策略引用了不同的正式集")

        checkpoint2_path = (
            run_dir / "checkpoints" / "checkpoint_2" / "report.json"
        )
        if not checkpoint2_path.is_file():
            raise FileNotFoundError("缺少检查点2报告")
        checkpoint2 = _require_mapping(
            read_json(checkpoint2_path),
            "checkpoint_2/report.json",
        )
        if checkpoint2.get("status") not in {"passed", "warning"}:
            raise GateCalibrationError("检查点2状态不允许进入阈值校准")

        matrix, chunks, index_manifest = load_validated_index(run_dir, config)
        if freeze.get("source_commit") != calibration.source_commit:
            raise GateCalibrationError("H2冻结Commit与校准集不一致")
        if freeze.get("corpus_sha256") != calibration.corpus_sha256:
            raise GateCalibrationError("H2冻结语料哈希与校准集不一致")
        if freeze.get("corpus_sha256") != index_manifest.get("corpus_sha256"):
            raise GateCalibrationError("H2冻结语料哈希与索引不一致")
        if freeze.get("index_sha256") != index_manifest.get(
            "embeddings_sha256"
        ):
            raise GateCalibrationError("H2冻结索引哈希与当前索引不一致")
        if freeze.get("model_revision") != config.revision:
            raise GateCalibrationError("H2冻结模型Revision与当前配置不一致")

        dependencies = installed_dependency_versions(config)
        snapshot_dir = snapshot_locator(config)
        verified_files = verify_required_model_files(snapshot_dir, config)
        backend = backend_factory(snapshot_dir, config, frozen_device)
        queries = [normalize_query(item.question) for item in calibration.questions]
        query_matrix, diagnostics = backend.encode_queries(
            queries,
            config.batch_size_for(frozen_device),
        )
        norm_diagnostics = validate_embedding_matrix(
            query_matrix,
            len(queries),
            config,
        )
        records = _top1_records(
            calibration.questions,
            query_matrix,
            matrix,
            chunks,
        )
        scores = [item["top1_score"] for item in records]
        scopes = [item["scope"] for item in records]
        minimum_recall = float(
            policy["algorithm"]["minimum_in_scope_recall"]
        )
        selected, candidates, reason = select_threshold(
            scores,
            scopes,
            minimum_recall,
        )
        for item in records:
            item["gate_decision"] = (
                "pass"
                if item["top1_score"] >= selected.threshold
                else "reject"
            )
            item["gate_correct"] = (
                item["gate_decision"] == item["expected_gate_decision"]
            )

        summary = {
            "schema_version": "retrieval_gate_threshold_v1",
            "experiment_run_id": run_dir.name,
            "computed_at": datetime.now().astimezone().isoformat(),
            "status": "computed_pending_h3_confirmation",
            "selected_threshold": selected.threshold,
            "selected_metrics": selected.as_dict(),
            "selection_reason": reason,
            "candidate_threshold_count": len(candidates),
            "minimum_in_scope_recall": minimum_recall,
            "calibration_question_count": len(records),
            "calibration_question_set_sha256": freeze["calibration_set"][
                "sha256"
            ],
            "evaluation_question_set_sha256": freeze["evaluation_set"][
                "sha256"
            ],
            "gate_policy_sha256": freeze["gate_policy"]["sha256"],
            "index_sha256": index_manifest["embeddings_sha256"],
            "corpus_sha256": index_manifest["corpus_sha256"],
            "model_id": config.model_id,
            "model_revision": config.revision,
            "device": frozen_device,
            "query_embedding_diagnostics": diagnostics,
            "query_norm_diagnostics": norm_diagnostics,
            "verified_model_files": verified_files,
            "dependencies": dependencies,
            "elapsed_seconds": round(time.perf_counter() - started, 6),
            "online_model_called": False,
            "evaluation_question_file_deserialized": False,
            "evaluation_embedding_called": False,
            "evaluation_retrieval_called": False,
        }
        calibration_dir = run_dir / "calibration"
        calibration_dir.mkdir(parents=True, exist_ok=True)
        staging_dir = Path(
            tempfile.mkdtemp(prefix=".threshold.", dir=calibration_dir)
        )
        write_json_atomic(
            staging_dir / "calibration_retrieval.json",
            {
                "schema_version": "calibration_retrieval_v1",
                "experiment_run_id": run_dir.name,
                "selected_threshold": selected.threshold,
                "records": records,
            },
        )
        write_json_atomic(
            staging_dir / "candidate_thresholds.json",
            {
                "schema_version": "candidate_threshold_metrics_v1",
                "selection_algorithm": policy["algorithm"],
                "candidates": [item.as_dict() for item in candidates],
            },
        )
        write_json_atomic(staging_dir / "threshold.json", summary)
        write_text_atomic(
            staging_dir / "report.md",
            _render_report(summary, records),
        )
        os.replace(staging_dir, output_dir)
        staging_dir = None
        return summary
    except Exception as error:
        if staging_dir is not None:
            shutil.rmtree(staging_dir, ignore_errors=True)
        try:
            _record_failure(run_dir, error)
        except OSError:
            pass
        raise
    finally:
        if backend is not None:
            backend.close()
