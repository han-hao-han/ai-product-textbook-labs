from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Sequence

from .embedding_config import EmbeddingConfig, load_embedding_config
from .embedding_model import (
    TransformerEmbeddingBackend,
    installed_dependency_versions,
    normalize_query,
    validate_embedding_matrix,
    verify_required_model_files,
)
from .gate_calibration import validate_h2_freeze
from .generation_client import (
    AliyunGenerationClient,
    GenerationBackend,
    read_generation_state,
)
from .generation_config import load_generation_config
from .h2_questions import H2Question, H2QuestionSet, load_h2_question_set
from .index_builder import _local_snapshot
from .io_utils import (
    read_json,
    sha256_file,
    write_json_atomic,
)
from .paths import EVALUATION_QUESTIONS_PATH
from .project_environment import load_project_environment
from .rag_pipeline import FINAL_STATES, run_rag_query
from .retriever import load_validated_index
from .retrieval_gate import load_retrieval_gate, validate_gate_against_index
from .run_state import load_run_manifest


class EvaluationError(RuntimeError):
    """Raised when the frozen formal evaluation cannot continue safely."""


def _hit(chunk: dict[str, Any], score: float, row: int, rank: int) -> dict[str, Any]:
    return {
        "rank": rank,
        "score": score,
        "row_index": row,
        "chunk_id": chunk["chunk_id"],
        "page_title": chunk["page_title"],
        "section_path": chunk["section_path"],
        "section_paths": chunk["section_paths"],
        "source_path": chunk["source_path"],
        "source_url": chunk["source_url"],
        "chunk_index": chunk["chunk_index"],
        "token_count": chunk["token_count"],
        "contains_code": chunk["contains_code"],
        "contains_table": chunk["contains_table"],
        "content_sha256": chunk["content_sha256"],
        "content": chunk["content"],
    }


def build_batch_retrieval(
    run_dir: Path,
    questions: Sequence[H2Question],
    config: EmbeddingConfig,
    frozen_device: str,
    *,
    top_k: int = 5,
    snapshot_locator: Callable[[EmbeddingConfig], Path] = _local_snapshot,
    backend_factory: Callable[
        [Path, EmbeddingConfig, str],
        TransformerEmbeddingBackend,
    ] = TransformerEmbeddingBackend,
) -> dict[str, Any]:
    import numpy as np

    if top_k != 5:
        raise ValueError("正式评价Top k必须固定为5")
    matrix, chunks, index_manifest = load_validated_index(run_dir, config)
    snapshot_dir = snapshot_locator(config)
    verify_required_model_files(snapshot_dir, config)
    dependencies = installed_dependency_versions(config)
    backend = backend_factory(snapshot_dir, config, frozen_device)
    started = time.perf_counter()
    try:
        queries = [normalize_query(item.question) for item in questions]
        query_matrix, diagnostics = backend.encode_queries(
            queries,
            config.batch_size_for(frozen_device),
        )
        norms = validate_embedding_matrix(query_matrix, len(queries), config)
        score_matrix = query_matrix @ matrix.T
        if not np.isfinite(score_matrix).all():
            raise EvaluationError("正式评价相似度包含NaN或Infinity")
        records: list[dict[str, Any]] = []
        for row, question in enumerate(questions):
            indices = np.argsort(
                -score_matrix[row],
                kind="stable",
            )[:top_k].tolist()
            hits = [
                _hit(
                    chunks[index],
                    float(score_matrix[row, index]),
                    index,
                    rank,
                )
                for rank, index in enumerate(indices, start=1)
            ]
            records.append(
                {
                    "schema_version": "retrieval_demo_v1",
                    "experiment_run_id": run_dir.name,
                    "created_at": datetime.now().astimezone().isoformat(),
                    "status": "passed",
                    "question_id": question.question_id,
                    "query": queries[row],
                    "query_instruction": config.query_instruction,
                    "query_template": config.query_template,
                    "model_id": config.model_id,
                    "revision": config.revision,
                    "device": frozen_device,
                    "top_k": top_k,
                    "similarity": index_manifest["similarity"],
                    "query_embedding_diagnostics": {
                        **diagnostics,
                        "batch_question_count": len(questions),
                    },
                    "top1_score": hits[0]["score"],
                    "hits": hits,
                    "dependencies": dependencies,
                    "elapsed_seconds": 0.0,
                    "generation_model_called": False,
                }
            )
    finally:
        backend.close()
    return {
        "schema_version": "formal_evaluation_retrieval_batch_v1",
        "experiment_run_id": run_dir.name,
        "created_at": datetime.now().astimezone().isoformat(),
        "question_count": len(questions),
        "top_k": top_k,
        "model_revision": config.revision,
        "index_sha256": index_manifest["embeddings_sha256"],
        "corpus_sha256": index_manifest["corpus_sha256"],
        "query_diagnostics": diagnostics,
        "norm_diagnostics": norms,
        "elapsed_seconds": round(time.perf_counter() - started, 6),
        "records": records,
    }


def _retrieval_comparison(
    question: H2Question,
    hits: list[dict[str, Any]],
) -> dict[str, Any]:
    if question.scope != "in_scope":
        return {
            "applicable": False,
            "single_source": False,
            "top1_reasonable_hit": None,
            "top5_source_status": "not_applicable",
            "matched_paths": [],
            "required_groups": [],
        }
    top1_path = str(hits[0]["source_path"])
    top5_paths = {str(hit["source_path"]) for hit in hits}
    groups = [
        {
            "group_id": group.group_id,
            "paths": list(group.paths),
            "matched_paths": sorted(set(group.paths) & top5_paths),
            "fully_matched": set(group.paths) <= top5_paths,
        }
        for group in question.acceptable_source_groups
    ]
    full = any(item["fully_matched"] for item in groups)
    any_match = any(item["matched_paths"] for item in groups)
    single_source = (
        len(question.acceptable_source_groups) == 1
        and len(question.acceptable_source_groups[0].paths) == 1
    )
    acceptable_top1 = {
        path
        for group in question.acceptable_source_groups
        for path in group.paths
    }
    return {
        "applicable": True,
        "single_source": single_source,
        "top1_reasonable_hit": (
            top1_path in acceptable_top1 if single_source else None
        ),
        "top5_source_status": (
            "full" if full else "partial" if any_match else "miss"
        ),
        "matched_paths": sorted(top5_paths & acceptable_top1),
        "required_groups": groups,
    }


def _classification_comparison(
    question: H2Question,
    result: dict[str, Any],
) -> dict[str, Any]:
    if question.scope != "in_scope":
        return {
            "applicable": False,
            "expected": None,
            "actual": None,
            "strict_correct": None,
            "acceptable_correct": None,
            "classification_failed": False,
        }
    classification = result.get("classification")
    if not isinstance(classification, dict):
        actual = None
        fallback = False
    else:
        actual = classification.get("question_type")
        fallback = bool(classification.get("fallback"))
    strict = actual == question.question_type and not fallback
    acceptable = actual == question.question_type
    return {
        "applicable": True,
        "expected": question.question_type,
        "actual": actual,
        "strict_correct": strict,
        "acceptable_correct": acceptable,
        "classification_failed": actual is None or fallback,
        "acceptable_rule": (
            "effective_type_matches_frozen_label_including_comprehensive_fallback"
        ),
    }


def _refusal_comparison(
    question: H2Question,
    result: dict[str, Any],
) -> dict[str, Any]:
    if question.scope == "in_scope":
        return {
            "applicable": False,
            "refusal_correct": None,
            "mechanism_conforming": None,
            "expected_mechanism": None,
        }
    final_state = str(result["final_state"])
    refusal_correct = final_state in {
        "retrieval_rejected",
        "model_refused",
    }
    expected_mechanism = (
        "model_refused"
        if question.scope == "boundary"
        else "retrieval_rejected"
    )
    return {
        "applicable": True,
        "refusal_correct": refusal_correct,
        "mechanism_conforming": final_state == expected_mechanism,
        "expected_mechanism": expected_mechanism,
    }


def compare_formal_result(
    question: H2Question,
    result: dict[str, Any],
) -> dict[str, Any]:
    retrieval = result.get("retrieval")
    hits = (
        retrieval.get("hits", [])
        if isinstance(retrieval, dict)
        else []
    )
    if len(hits) != 5:
        raise EvaluationError("正式题没有完整Top 5检索结果")
    return {
        "schema_version": "formal_evaluation_comparison_v1",
        "question_id": question.question_id,
        "scope": question.scope,
        "program_does_not_grade_answer_semantics": True,
        "retrieval": _retrieval_comparison(question, hits),
        "classification": _classification_comparison(question, result),
        "refusal": _refusal_comparison(question, result),
    }


def _load_question_set() -> tuple[H2QuestionSet, dict[str, Any]]:
    freeze = validate_h2_freeze()
    questions = load_h2_question_set(EVALUATION_QUESTIONS_PATH)
    if questions.set_role != "evaluation" or len(questions.questions) != 30:
        raise EvaluationError("冻结正式集必须包含30道evaluation题")
    if questions.sha256 != freeze["evaluation_set"]["sha256"]:
        raise EvaluationError("正式题集SHA-256与H2冻结清单不一致")
    return questions, freeze


def _load_or_build_retrieval(
    run_dir: Path,
    question_set: H2QuestionSet,
    config: EmbeddingConfig,
    frozen_device: str,
) -> dict[str, Any]:
    path = run_dir / "evaluation" / "retrieval_batch.json"
    if path.is_file():
        payload = read_json(path)
        if (
            payload.get("question_set_sha256") != question_set.sha256
            or payload.get("question_count") != 30
            or payload.get("top_k") != 5
        ):
            raise EvaluationError("已有正式检索批次与冻结题集不一致")
        return payload
    payload = build_batch_retrieval(
        run_dir,
        question_set.questions,
        config,
        frozen_device,
    )
    payload["question_set_sha256"] = question_set.sha256
    write_json_atomic(path, payload)
    return payload


def _persist_question_attempt(
    run_dir: Path,
    question: H2Question,
    result: dict[str, Any],
    comparison: dict[str, Any],
    question_set_sha256: str,
) -> None:
    question_dir = run_dir / "evaluation" / "questions" / question.question_id
    question_dir.mkdir(parents=True, exist_ok=True)
    attempt_dir = question_dir / "attempt_001"
    if attempt_dir.exists():
        raise FileExistsError(f"{question.question_id}/attempt_001已存在")
    staging = Path(
        tempfile.mkdtemp(prefix=".attempt_001.", dir=question_dir)
    )
    try:
        result["formal_evaluation"] = {
            "question_id": question.question_id,
            "scope": question.scope,
            "question_type": question.question_type,
            "question_set_sha256": question_set_sha256,
            "attempt": "attempt_001",
        }
        write_json_atomic(staging / "result.json", result)
        write_json_atomic(
            staging / "raw_responses.json",
            {
                "schema_version": "formal_raw_responses_v1",
                "question_id": question.question_id,
                "responses": result["generation"]["raw_responses"],
                "api_key_saved": False,
            },
        )
        write_json_atomic(
            staging / "parsed_result.json",
            {
                "schema_version": "formal_parsed_result_v1",
                "question_id": question.question_id,
                "classification": result.get("classification"),
                "answer": result.get("answer"),
                "citations": result.get("citations", []),
                "final_state": result["final_state"],
            },
        )
        write_json_atomic(staging / "comparison.json", comparison)
        os.replace(staging, attempt_dir)
    except Exception:
        if staging.resolve().parent == question_dir.resolve():
            shutil.rmtree(staging, ignore_errors=True)
        raise


def _existing_attempt(
    run_dir: Path,
    question: H2Question,
    question_set_sha256: str,
) -> dict[str, Any] | None:
    attempt_dir = (
        run_dir
        / "evaluation"
        / "questions"
        / question.question_id
        / "attempt_001"
    )
    if not attempt_dir.exists():
        return None
    result_path = attempt_dir / "result.json"
    comparison_path = attempt_dir / "comparison.json"
    if not result_path.is_file() or not comparison_path.is_file():
        raise EvaluationError(
            f"{question.question_id}/attempt_001不完整，拒绝覆盖"
        )
    result = read_json(result_path)
    formal = result.get("formal_evaluation", {})
    if (
        formal.get("question_id") != question.question_id
        or formal.get("question_set_sha256") != question_set_sha256
        or result.get("final_state") not in FINAL_STATES
    ):
        raise EvaluationError(f"{question.question_id}/attempt_001校验失败")
    return result


def _evaluation_summary(
    run_dir: Path,
    question_set: H2QuestionSet,
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for question in question_set.questions:
        attempt = (
            run_dir
            / "evaluation"
            / "questions"
            / question.question_id
            / "attempt_001"
        )
        if not (attempt / "result.json").is_file():
            continue
        result = read_json(attempt / "result.json")
        comparison = read_json(attempt / "comparison.json")
        records.append(
            {
                "question_id": question.question_id,
                "scope": question.scope,
                "final_state": result["final_state"],
                "online_model_called": result["generation"][
                    "online_model_called"
                ],
                "program_comparison": comparison,
                "attempt_path": (
                    f"evaluation/questions/{question.question_id}/attempt_001"
                ),
            }
        )
    complete = len(records) == len(question_set.questions)
    failure_states = {
        "generation_failed",
        "validation_failed",
        "retrieval_only",
    }
    has_runtime_failure = any(
        item["final_state"] in failure_states for item in records
    )
    return {
        "schema_version": "formal_evaluation_summary_v1",
        "experiment_run_id": run_dir.name,
        "created_at": datetime.now().astimezone().isoformat(),
        "status": (
            "warning"
            if complete and has_runtime_failure
            else "passed"
            if complete
            else "blocked"
        ),
        "question_set_sha256": question_set.sha256,
        "formal_metrics_attempt": "attempt_001",
        "question_count": len(question_set.questions),
        "completed_count": len(records),
        "remaining_count": len(question_set.questions) - len(records),
        "final_states": dict(Counter(item["final_state"] for item in records)),
        "online_generation_question_count": sum(
            bool(item["online_model_called"]) for item in records
        ),
        "records": records,
    }


def run_formal_evaluation(
    run_dir: Path,
    *,
    generation_backend: GenerationBackend | None = None,
    environment: dict[str, str] | None = None,
    progress: Callable[[int, int, str, str], None] | None = None,
) -> dict[str, Any]:
    question_set, freeze = _load_question_set()
    manifest = load_run_manifest(run_dir)
    checkpoint3_path = (
        run_dir / "checkpoints" / "checkpoint_3" / "report.json"
    )
    if not checkpoint3_path.is_file():
        raise FileNotFoundError("缺少检查点3报告")
    if read_json(checkpoint3_path).get("status") != "passed":
        raise EvaluationError("检查点3尚未通过")
    config = load_embedding_config()
    gate = load_retrieval_gate()
    index_manifest = read_json(
        run_dir / "index" / "current" / "index_manifest.json"
    )
    validate_gate_against_index(gate, index_manifest)
    if gate.evaluation_set_sha256 != question_set.sha256:
        raise EvaluationError("门控冻结的正式题集SHA-256不一致")
    if freeze["index_sha256"] != index_manifest["embeddings_sha256"]:
        raise EvaluationError("H2冻结索引与当前索引不一致")

    state = read_generation_state(run_dir)
    if state.get("status") != "passed":
        raise EvaluationError("生成客户端状态不是passed")
    generation_config = load_generation_config()
    if environment is None:
        load_project_environment(
            variable_name=generation_config.api_key_environment_variable
        )
        env = os.environ
    else:
        env = environment
    api_key = str(
        env.get(generation_config.api_key_environment_variable, "")
    ).strip()
    if generation_backend is None and not api_key:
        raise EvaluationError("正式评价缺少百炼API Key")
    backend = generation_backend or AliyunGenerationClient(
        generation_config,
        api_key,
    )

    retrieval_batch = _load_or_build_retrieval(
        run_dir,
        question_set,
        config,
        str(manifest["frozen_device"]),
    )
    records_by_query = {
        str(item["query"]): item for item in retrieval_batch["records"]
    }

    def cached_retrieval(
        _run_dir: Path,
        _config: EmbeddingConfig,
        _device: str,
        query: str,
        *,
        top_k: int,
    ) -> dict[str, Any]:
        if top_k != 5 or query not in records_by_query:
            raise EvaluationError("正式评价检索缓存未命中")
        return records_by_query[query]

    total = len(question_set.questions)
    for position, question in enumerate(question_set.questions, start=1):
        existing = _existing_attempt(
            run_dir,
            question,
            question_set.sha256,
        )
        if existing is not None:
            if progress:
                progress(position, total, question.question_id, "skipped")
            continue
        result = run_rag_query(
            run_dir,
            question.question,
            top_k=5,
            retrieval_function=cached_retrieval,
            generation_backend=backend,
            environment=env,
        )
        comparison = compare_formal_result(question, result)
        _persist_question_attempt(
            run_dir,
            question,
            result,
            comparison,
            question_set.sha256,
        )
        if progress:
            progress(
                position,
                total,
                question.question_id,
                str(result["final_state"]),
            )
        if (
            result["final_state"] == "generation_failed"
            and read_generation_state(run_dir).get("status") == "blocked"
        ):
            break

    summary = _evaluation_summary(run_dir, question_set)
    write_json_atomic(run_dir / "evaluation" / "summary.json", summary)
    return summary
