from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .embedding_config import load_embedding_config
from .embedding_model import normalize_query
from .evidence_excerpt import select_evidence_excerpt
from .generation_client import (
    AliyunGenerationClient,
    CompletionRecord,
    GenerationBackend,
    GenerationCallError,
    StructuredResponseError,
    read_generation_state,
)
from .generation_config import load_generation_config
from .generation_schemas import (
    QuestionType,
    validate_answer_markdown,
    validate_citations,
)
from .io_utils import read_json, write_json_atomic
from .paths import PROJECT_ROOT
from .project_environment import load_project_environment
from .retrieval_gate import (
    load_retrieval_gate,
    validate_gate_against_index,
)
from .retriever import retrieve_top_k
from .run_state import load_run_manifest


FINAL_STATES = {
    "retrieval_rejected",
    "model_refused",
    "answered",
    "generation_failed",
    "validation_failed",
    "retrieval_only",
}


def normalize_and_validate_question(question: str) -> str:
    normalized = normalize_query(question)
    if len(normalized) > 2000:
        raise ValueError("问题超过2000字符；输入不会被截断")
    return normalized


def _phase(
    name: str,
    status: str,
    elapsed_seconds: float | None = None,
    **details: Any,
) -> dict[str, Any]:
    result: dict[str, Any] = {"name": name, "status": status}
    if elapsed_seconds is not None:
        result["elapsed_seconds"] = round(elapsed_seconds, 6)
    result.update(details)
    return result


def _append_skipped(phases: list[dict[str, Any]], names: list[str]) -> None:
    phases.extend(_phase(name, "skipped") for name in names)


def _sanitize_message(message: str) -> str:
    sanitized = message
    for path in (Path.home(), PROJECT_ROOT):
        sanitized = sanitized.replace(str(path), "<LOCAL_PATH>")
    return sanitized[:4000]


def _record_runtime_incident(
    run_dir: Path,
    error: Exception,
    *,
    stage: str,
    fatal: bool,
) -> Path:
    directory = run_dir / "generation" / "runtime_incidents"
    directory.mkdir(parents=True, exist_ok=True)
    existing = sorted(directory.glob("incident_*.json"))
    path = directory / f"incident_{len(existing) + 1:03d}.json"
    write_json_atomic(
        path,
        {
            "schema_version": "generation_runtime_incident_v1",
            "experiment_run_id": run_dir.name,
            "created_at": datetime.now().astimezone().isoformat(),
            "stage": stage,
            "fatal": fatal,
            "error_type": type(error).__name__,
            "error_message": _sanitize_message(str(error)),
            "status_code": getattr(error, "status_code", None),
            "temporary": getattr(error, "temporary", False),
            "api_key_saved": False,
        },
    )
    if fatal:
        current = read_generation_state(run_dir)
        current.update(
            {
                "updated_at": datetime.now().astimezone().isoformat(),
                "status": "blocked",
                "reason": "fatal_runtime_generation_error",
                "online_calls_allowed": False,
                "latest_incident": path.name,
            }
        )
        write_json_atomic(
            run_dir / "generation" / "current_state.json",
            current,
        )
    return path


def _finish(
    result: dict[str, Any],
    final_state: str,
    started: float,
) -> dict[str, Any]:
    if final_state not in FINAL_STATES:
        raise ValueError(f"未知最终状态：{final_state}")
    result["final_state"] = final_state
    result["total_elapsed_seconds"] = round(time.perf_counter() - started, 6)
    return result


def _citations(
    answer_text: str,
    question: str,
    cited_ids: list[str],
    hits: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_id = {str(hit["chunk_id"]): hit for hit in hits}
    citations: list[dict[str, Any]] = []
    for chunk_id in cited_ids:
        hit = by_id[chunk_id]
        excerpt = select_evidence_excerpt(
            str(hit["content"]),
            question,
            answer_text,
        )
        citations.append(
            {
                "chunk_id": chunk_id,
                "page_title": hit["page_title"],
                "section_path": hit["section_path"],
                "source_path": hit["source_path"],
                "source_url": hit["source_url"],
                **excerpt,
            }
        )
    return citations


def run_rag_query(
    run_dir: Path,
    question: str,
    *,
    top_k: int = 5,
    retrieval_function: Callable[..., dict[str, Any]] = retrieve_top_k,
    generation_backend: GenerationBackend | None = None,
    environment: dict[str, str] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    normalized = normalize_and_validate_question(question)
    if top_k < 3 or top_k > 8:
        raise ValueError("Streamlit探索top_k必须位于3～8")
    embedding_config = load_embedding_config()
    generation_config = load_generation_config()
    gate = load_retrieval_gate()
    run_manifest = load_run_manifest(run_dir)
    if gate.source_commit != run_manifest.get("source_commit"):
        raise ValueError("正式门控Commit与当前运行不一致")
    index_manifest = read_json(
        run_dir / "index" / "current" / "index_manifest.json"
    )
    validate_gate_against_index(gate, index_manifest)
    phases: list[dict[str, Any]] = []
    result: dict[str, Any] = {
        "schema_version": "interactive_rag_result_v1",
        "experiment_run_id": run_dir.name,
        "created_at": datetime.now().astimezone().isoformat(),
        "question": normalized,
        "top_k": top_k,
        "threshold": gate.threshold,
        "phases": phases,
        "retrieval": None,
        "classification": None,
        "answer": None,
        "citations": [],
        "validation_warnings": [],
        "generation": {
            "online_model_called": False,
            "raw_responses": [],
            "evidence_sent": [],
        },
    }

    retrieval_started = time.perf_counter()
    retrieval = retrieval_function(
        run_dir,
        embedding_config,
        str(run_manifest["frozen_device"]),
        normalized,
        top_k=top_k,
    )
    retrieval_elapsed = time.perf_counter() - retrieval_started
    result["retrieval"] = retrieval
    phases.extend(
        [
            _phase(
                "query_embedding",
                "completed",
                retrieval_elapsed,
                diagnostics=retrieval.get("query_embedding_diagnostics"),
            ),
            _phase(
                "retrieval",
                "completed",
                retrieval_elapsed,
                top_k=top_k,
            ),
        ]
    )

    gate_started = time.perf_counter()
    gate_passed = gate.passes(float(retrieval["top1_score"]))
    phases.append(
        _phase(
            "retrieval_gate",
            "completed" if gate_passed else "rejected",
            time.perf_counter() - gate_started,
            top1_score=float(retrieval["top1_score"]),
            threshold=gate.threshold,
            passed=gate_passed,
        )
    )
    if not gate_passed:
        _append_skipped(
            phases,
            ["classification", "structured_generation", "validation"],
        )
        phases.append(_phase("final", "rejected"))
        return _finish(result, "retrieval_rejected", started)

    state = read_generation_state(run_dir)
    if environment is None:
        load_project_environment(
            variable_name=generation_config.api_key_environment_variable,
        )
        env = os.environ
    else:
        env = environment
    api_key = str(
        env.get(generation_config.api_key_environment_variable, "")
    ).strip()
    if generation_backend is None and (
        state.get("status") != "passed" or not api_key
    ):
        _append_skipped(
            phases,
            ["classification", "structured_generation", "validation"],
        )
        phases.append(
            _phase(
                "final",
                "completed",
                generation_state=state.get("status"),
                api_key_present=bool(api_key),
            )
        )
        return _finish(result, "retrieval_only", started)
    backend = generation_backend or AliyunGenerationClient(
        generation_config,
        api_key,
    )

    classification_started = time.perf_counter()
    question_type = QuestionType.comprehensive.value
    classification_fallback = False
    try:
        classification, classification_record = backend.classify(normalized)
        question_type = classification.question_type.value
        result["classification"] = {
            "question_type": question_type,
            "fallback": False,
        }
        result["generation"]["online_model_called"] = True
        result["generation"]["raw_responses"].append(
            classification_record.as_dict()
        )
        phases.append(
            _phase(
                "classification",
                "completed",
                time.perf_counter() - classification_started,
                attempts=classification_record.attempts,
            )
        )
    except StructuredResponseError as error:
        classification_fallback = True
        if error.record is not None:
            result["generation"]["online_model_called"] = True
            result["generation"]["raw_responses"].append(
                error.record.as_dict()
            )
        result["classification"] = {
            "question_type": question_type,
            "fallback": True,
            "error": _sanitize_message(str(error)),
        }
        phases.append(
            _phase(
                "classification",
                "failed",
                time.perf_counter() - classification_started,
                fallback="comprehensive",
            )
        )
    except GenerationCallError as error:
        result["generation"]["online_model_called"] = True
        if error.fatal:
            incident = _record_runtime_incident(
                run_dir,
                error,
                stage="classification",
                fatal=True,
            )
            result["generation"]["error"] = _sanitize_message(str(error))
            result["generation"]["incident"] = incident.name
            phases.append(
                _phase(
                    "classification",
                    "failed",
                    time.perf_counter() - classification_started,
                    attempts=error.attempts,
                )
            )
            _append_skipped(
                phases,
                ["structured_generation", "validation"],
            )
            phases.append(_phase("final", "failed"))
            return _finish(result, "generation_failed", started)
        classification_fallback = True
        result["classification"] = {
            "question_type": question_type,
            "fallback": True,
            "error": _sanitize_message(str(error)),
        }
        phases.append(
            _phase(
                "classification",
                "failed",
                time.perf_counter() - classification_started,
                attempts=error.attempts,
                fallback="comprehensive",
            )
        )

    generation_started = time.perf_counter()
    try:
        parsed_answer, answer_record, evidence_sent = backend.answer(
            normalized,
            question_type,
            retrieval["hits"],
        )
        result["generation"]["online_model_called"] = True
        result["generation"]["raw_responses"].append(answer_record.as_dict())
        result["generation"]["evidence_sent"] = evidence_sent
        result["answer"] = parsed_answer.model_dump(mode="json")
        phases.append(
            _phase(
                "structured_generation",
                "completed",
                time.perf_counter() - generation_started,
                attempts=answer_record.attempts,
                classification_fallback=classification_fallback,
            )
        )
    except StructuredResponseError as error:
        if error.record is not None:
            result["generation"]["online_model_called"] = True
            result["generation"]["raw_responses"].append(
                error.record.as_dict()
            )
        result["generation"]["error"] = _sanitize_message(str(error))
        phases.append(
            _phase(
                "structured_generation",
                "completed",
                time.perf_counter() - generation_started,
            )
        )
        phases.append(_phase("validation", "failed"))
        phases.append(_phase("final", "failed"))
        return _finish(result, "validation_failed", started)
    except GenerationCallError as error:
        result["generation"]["online_model_called"] = True
        incident = _record_runtime_incident(
            run_dir,
            error,
            stage="structured_generation",
            fatal=error.fatal,
        )
        result["generation"]["error"] = _sanitize_message(str(error))
        result["generation"]["incident"] = incident.name
        phases.append(
            _phase(
                "structured_generation",
                "failed",
                time.perf_counter() - generation_started,
                attempts=error.attempts,
            )
        )
        _append_skipped(phases, ["validation"])
        phases.append(_phase("final", "failed"))
        return _finish(result, "generation_failed", started)

    validation_started = time.perf_counter()
    try:
        validate_citations(
            parsed_answer,
            {str(hit["chunk_id"]) for hit in retrieval["hits"]},
        )
        if parsed_answer.answerable:
            warnings = validate_answer_markdown(str(parsed_answer.answer))
            result["validation_warnings"] = warnings
            result["citations"] = _citations(
                str(parsed_answer.answer),
                normalized,
                list(parsed_answer.cited_chunk_ids),
                retrieval["hits"],
            )
            final_state = "answered"
        else:
            validate_answer_markdown(str(parsed_answer.refusal_reason))
            final_state = "model_refused"
        phases.append(
            _phase(
                "validation",
                "completed",
                time.perf_counter() - validation_started,
                warnings=len(result["validation_warnings"]),
            )
        )
    except (KeyError, TypeError, ValueError) as error:
        result["generation"]["error"] = _sanitize_message(str(error))
        phases.append(
            _phase(
                "validation",
                "failed",
                time.perf_counter() - validation_started,
            )
        )
        phases.append(_phase("final", "failed"))
        return _finish(result, "validation_failed", started)
    phases.append(_phase("final", "completed"))
    return _finish(result, final_state, started)
