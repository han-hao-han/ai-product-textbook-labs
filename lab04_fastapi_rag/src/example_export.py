from __future__ import annotations

import os
import re
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from .io_utils import (
    read_json,
    sha256_file,
    write_json_atomic,
    write_text_atomic,
)
from .paths import CHECKPOINT_EXAMPLES_DIR, EXAMPLE_CANDIDATES_DIR, PROJECT_ROOT


CHECKPOINT_NAMES = tuple(f"checkpoint_{index}" for index in range(1, 5))
INTERACTIVE_FILES = (
    "result.json",
    "result.md",
    "retrieval_results.json",
    "generation_context.json",
    "snapshot_metadata.json",
)
SECRET_PATTERNS = (
    re.compile(r"(?i)authorization\s*[:=]\s*bearer\s+\S+"),
    re.compile(r"(?i)DASHSCOPE_API_KEY\s*=\s*\S+"),
    re.compile(r"(?i)\bsk-[a-z0-9_-]{12,}\b"),
)
LOCAL_PATH_MARKERS = tuple(
    {
        str(PROJECT_ROOT),
        PROJECT_ROOT.as_posix(),
        str(Path.home()),
        Path.home().as_posix(),
    }
)


class ExampleExportError(RuntimeError):
    """Raised when example candidates cannot be exported safely."""


def _relative_to_project(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def _assert_public_text(text: str, label: str) -> None:
    folded = text.casefold()
    if any(marker.casefold() in folded for marker in LOCAL_PATH_MARKERS):
        raise ExampleExportError(f"{label}包含当前项目或用户的本地绝对路径")
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            raise ExampleExportError(f"{label}包含疑似凭据或请求头")


def _iter_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _iter_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_strings(item)


def _assert_public_file(path: Path, label: str) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise ExampleExportError(f"{label}不是UTF-8文本文件") from error
    if path.suffix.lower() == ".json":
        payload = read_json(path)
        for value in _iter_strings(payload):
            _assert_public_text(value, label)
    else:
        _assert_public_text(text, label)


def _checkpoint_records(run_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for checkpoint in CHECKPOINT_NAMES:
        directory = run_dir / "checkpoints" / checkpoint
        json_path = directory / "report.json"
        md_path = directory / "report.md"
        if not json_path.is_file() or not md_path.is_file():
            raise FileNotFoundError(f"缺少{checkpoint}报告")
        report = read_json(json_path)
        if report.get("experiment_run_id") != run_dir.name:
            raise ExampleExportError(f"{checkpoint}不属于当前实验运行")
        if report.get("status") not in {"passed", "warning"}:
            raise ExampleExportError(f"{checkpoint}状态不可导出：{report.get('status')}")
        _assert_public_file(json_path, f"{checkpoint}/report.json")
        _assert_public_file(md_path, f"{checkpoint}/report.md")
        records.append(
            {
                "checkpoint": checkpoint,
                "status": report["status"],
                "report_json": (
                    f"checkpoints/{checkpoint}/report.json"
                ),
                "report_json_sha256": sha256_file(json_path),
                "report_md": f"checkpoints/{checkpoint}/report.md",
                "report_md_sha256": sha256_file(md_path),
            }
        )
    return records


def _judge_candidates(run_dir: Path) -> list[dict[str, Any]]:
    summary_path = run_dir / "judge" / "formal" / "summary.json"
    inputs_manifest_path = run_dir / "judge" / "inputs_v1" / "manifest.json"
    if not summary_path.is_file() or not inputs_manifest_path.is_file():
        raise FileNotFoundError("缺少正式Judge汇总或盲审输入manifest")
    summary = read_json(summary_path)
    inputs_manifest = read_json(inputs_manifest_path)
    if (
        summary.get("formal_metrics_attempt") != "attempt_001"
        or summary.get("status") not in {"passed", "warning"}
    ):
        raise ExampleExportError("正式Judge汇总不是可导出的attempt_001")
    input_paths = {
        item["question_id"]: run_dir / item["input_path"]
        for item in inputs_manifest["included"]
    }
    selected: list[dict[str, Any]] = []
    for wanted_grade in ("fully_correct", "mostly_correct", "incorrect"):
        match = next(
            (
                item
                for item in summary["records"]
                if item.get("status") == "judged"
                and item.get("answer_grade") == wanted_grade
            ),
            None,
        )
        if match is None:
            continue
        question_id = str(match["question_id"])
        attempt_dir = run_dir / str(match["attempt_path"])
        metadata_path = attempt_dir / "metadata.json"
        output_path = attempt_dir / "parsed_output.json"
        input_path = input_paths.get(question_id)
        if (
            input_path is None
            or not input_path.is_file()
            or not metadata_path.is_file()
            or not output_path.is_file()
        ):
            raise FileNotFoundError(f"{question_id}的首次Judge记录不完整")
        metadata = read_json(metadata_path)
        output = read_json(output_path)
        if (
            metadata.get("question_id") != question_id
            or metadata.get("attempt") != "attempt_001"
            or metadata.get("formal_evaluation") is not True
            or metadata.get("status") != "judged"
            or metadata.get("forbidden_events") != []
            or output.get("answer_grade") != wanted_grade
        ):
            raise ExampleExportError(f"{question_id}不是干净的首次正式审核")
        bundle = {
            "schema_version": "checkpoint_4_judge_example_v1",
            "experiment_run_id": run_dir.name,
            "question_id": question_id,
            "attempt": "attempt_001",
            "input": read_json(input_path),
            "judge_output": output,
            "provenance": {
                "status": metadata["status"],
                "model": metadata["model"],
                "reasoning_effort": metadata["reasoning_effort"],
                "cli_version": metadata["cli_version"],
                "sandbox": metadata["sandbox"],
                "ephemeral": metadata["ephemeral"],
                "automatic_retries": metadata["automatic_retries"],
                "input_sha256": metadata["input_sha256"],
                "prompt_sha256": metadata["prompt_sha256"],
                "forbidden_events": metadata["forbidden_events"],
                "credential_saved": metadata["credential_saved"],
            },
        }
        selected.append(
            {
                "question_id": question_id,
                "answer_grade": wanted_grade,
                "bundle": bundle,
            }
        )
        if len(selected) == 3:
            break
    if not selected:
        raise ExampleExportError("没有可用的真实Judge首次审核示例")
    return selected


def build_example_candidates(
    run_dir: Path,
    *,
    candidate_root: Path = EXAMPLE_CANDIDATES_DIR,
) -> Path:
    candidate_dir = candidate_root / run_dir.name
    if candidate_dir.exists():
        raise FileExistsError("示例候选目录已存在，拒绝覆盖")
    checkpoints = _checkpoint_records(run_dir)
    judge_candidates = _judge_candidates(run_dir)
    candidate_root.mkdir(parents=True, exist_ok=True)
    staging_dir = Path(
        tempfile.mkdtemp(prefix=f".{run_dir.name}.", dir=candidate_root)
    )
    try:
        judge_records = []
        for item in judge_candidates:
            question_id = item["question_id"]
            relative_path = f"judge/{question_id}.json"
            output_path = staging_dir / relative_path
            write_json_atomic(output_path, item["bundle"])
            _assert_public_file(output_path, relative_path)
            judge_records.append(
                {
                    "question_id": question_id,
                    "answer_grade": item["answer_grade"],
                    "candidate_path": relative_path,
                    "candidate_sha256": sha256_file(output_path),
                }
            )
        manifest = {
            "schema_version": "checkpoint_example_candidates_v1",
            "status": "pending_human_confirmation",
            "experiment_run_id": run_dir.name,
            "created_at": datetime.now().astimezone().isoformat(),
            "same_run_chain": True,
            "checkpoint_reports": checkpoints,
            "judge_candidates": judge_records,
            "selection_rule": (
                "按正式题顺序选取实际出现的每个回答等级的首个干净attempt_001，"
                "最多3个"
            ),
            "public_export_target": "results/checkpoints/examples",
            "human_confirmation_required_before_export": True,
            "results_may_vary": True,
        }
        write_json_atomic(staging_dir / "candidate_manifest.json", manifest)
        os.replace(staging_dir, candidate_dir)
        return candidate_dir
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise


def _verify_candidate_manifest(
    run_dir: Path,
    candidate_dir: Path,
) -> dict[str, Any]:
    manifest_path = candidate_dir / "candidate_manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError("缺少示例候选manifest")
    manifest = read_json(manifest_path)
    if (
        manifest.get("schema_version") != "checkpoint_example_candidates_v1"
        or manifest.get("status") != "pending_human_confirmation"
        or manifest.get("experiment_run_id") != run_dir.name
        or manifest.get("same_run_chain") is not True
    ):
        raise ExampleExportError("示例候选manifest无效")
    current_checkpoints = {
        item["checkpoint"]: item for item in _checkpoint_records(run_dir)
    }
    for frozen in manifest["checkpoint_reports"]:
        current = current_checkpoints.get(frozen["checkpoint"])
        if current != frozen:
            raise ExampleExportError(
                f"{frozen['checkpoint']}报告已在候选生成后变化"
            )
    for item in manifest["judge_candidates"]:
        path = candidate_dir / item["candidate_path"]
        if not path.is_file() or sha256_file(path) != item["candidate_sha256"]:
            raise ExampleExportError(
                f"{item['question_id']}候选已变化或缺失"
            )
        _assert_public_file(path, item["candidate_path"])
    return manifest


def export_checkpoint_examples(
    run_dir: Path,
    *,
    candidate_root: Path = EXAMPLE_CANDIDATES_DIR,
    target_dir: Path = CHECKPOINT_EXAMPLES_DIR,
) -> Path:
    if target_dir.exists():
        raise FileExistsError("公开示例目标目录已存在，拒绝覆盖")
    candidate_dir = candidate_root / run_dir.name
    manifest = _verify_candidate_manifest(run_dir, candidate_dir)
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    staging_dir = Path(
        tempfile.mkdtemp(prefix=".examples.", dir=target_dir.parent)
    )
    try:
        for item in manifest["checkpoint_reports"]:
            checkpoint = item["checkpoint"]
            source_dir = run_dir / "checkpoints" / checkpoint
            destination_dir = staging_dir / checkpoint
            destination_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_dir / "report.json", destination_dir / "report.json")
            shutil.copy2(source_dir / "report.md", destination_dir / "report.md")

        checkpoint3 = read_json(
            run_dir / "checkpoints" / "checkpoint_3" / "report.json"
        )
        for record in checkpoint3["reader_experience_records"]:
            source_dir = (run_dir / record["saved_result"]).parent
            destination_dir = (
                staging_dir
                / "checkpoint_3"
                / "interactive"
                / record["reader_experience_type"]
            )
            destination_dir.mkdir(parents=True, exist_ok=True)
            for name in INTERACTIVE_FILES:
                source_path = source_dir / name
                if not source_path.is_file():
                    raise FileNotFoundError(
                        f"检查点3示例缺少{name}"
                    )
                shutil.copy2(source_path, destination_dir / name)

        judge_dir = staging_dir / "checkpoint_4" / "judge_examples"
        judge_dir.mkdir(parents=True, exist_ok=True)
        for item in manifest["judge_candidates"]:
            shutil.copy2(
                candidate_dir / item["candidate_path"],
                judge_dir / f"{item['question_id']}.json",
            )

        for path in staging_dir.rglob("*"):
            if path.is_file():
                _assert_public_file(
                    path,
                    path.relative_to(staging_dir).as_posix(),
                )
        export_manifest = {
            "schema_version": "checkpoint_examples_v1",
            "experiment_run_id": run_dir.name,
            "exported_at": datetime.now().astimezone().isoformat(),
            "same_run_chain": True,
            "checkpoint_statuses": {
                item["checkpoint"]: item["status"]
                for item in manifest["checkpoint_reports"]
            },
            "judge_examples": [
                {
                    "question_id": item["question_id"],
                    "answer_grade": item["answer_grade"],
                }
                for item in manifest["judge_candidates"]
            ],
            "contains_api_key": False,
            "contains_authorization_header": False,
            "contains_local_absolute_path": False,
            "results_may_vary": True,
            "full_run_records_committed": False,
        }
        write_json_atomic(staging_dir / "manifest.json", export_manifest)
        write_text_atomic(
            staging_dir / "README.md",
            "\n".join(
                [
                    "# 检查点公开示例",
                    "",
                    f"这些文件来自同一实验运行`{run_dir.name}`，"
                    "没有拼接不同运行中的最佳结果。",
                    "",
                    "四组检查点报告、三类Streamlit现场结果和Codex Judge示例"
                    "均来自真实首次运行记录。完整运行目录、模型权重、API Key、"
                    "请求头和Judge stdout/stderr未导出。",
                    "",
                    "模型输出、网络状态和耗时可能波动。这里的结果只代表一次"
                    "冻结运行，不是模型的固定输出或普遍性能结论。",
                    "",
                    "FastAPI文档示例受MIT许可证约束；具体来源、版本和第三方"
                    "许可见项目根目录`THIRD_PARTY_NOTICES.md`。",
                    "",
                ]
            ),
        )
        os.replace(staging_dir, target_dir)
        return target_dir
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise
