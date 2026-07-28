from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .gate_calibration import validate_h2_freeze
from .h2_questions import H2Question, load_h2_question_set
from .io_utils import (
    read_json,
    sha256_text,
    write_json_atomic,
)
from .judge_client import BlindJudgeInput
from .paths import (
    EVALUATION_QUESTIONS_PATH,
    JUDGE_INPUTS_DIR_NAME,
)


BLIND_INPUT_KEYS = {
    "question_id",
    "question",
    "required_points",
    "optional_points",
    "critical_errors",
    "final_answer",
    "cited_chunks",
}
BLIND_CHUNK_KEYS = {
    "chunk_id",
    "source_path",
    "section_path",
    "content",
}


class JudgeInputError(RuntimeError):
    """Raised when a blind Judge input could leak forbidden evaluation data."""


def _input_hash(payload: dict[str, Any]) -> str:
    return sha256_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True)
    )


def _blind_input(
    question: H2Question,
    result: dict[str, Any],
) -> BlindJudgeInput:
    answer = result.get("answer")
    retrieval = result.get("retrieval")
    if (
        result.get("final_state") != "answered"
        or not isinstance(answer, dict)
        or answer.get("answerable") is not True
        or not isinstance(answer.get("answer"), str)
        or not isinstance(retrieval, dict)
    ):
        raise JudgeInputError(f"{question.question_id}不是可盲审的有效回答")
    cited_ids = answer.get("cited_chunk_ids")
    hits = retrieval.get("hits")
    if not isinstance(cited_ids, list) or not isinstance(hits, list):
        raise JudgeInputError(f"{question.question_id}缺少实际引用")
    by_id = {str(hit["chunk_id"]): hit for hit in hits}
    cited_chunks: list[dict[str, str]] = []
    for chunk_id in cited_ids:
        if str(chunk_id) not in by_id:
            raise JudgeInputError(f"{question.question_id}引用不在Top 5中")
        hit = by_id[str(chunk_id)]
        section = hit.get("section_path", [])
        section_text = (
            " > ".join(str(item) for item in section)
            if isinstance(section, list)
            else str(section)
        )
        cited_chunks.append(
            {
                "chunk_id": str(hit["chunk_id"]),
                "source_path": str(hit["source_path"]),
                "section_path": section_text,
                "content": str(hit["content"]),
            }
        )
    return BlindJudgeInput(
        question_id=question.question_id,
        question=question.question,
        required_points=question.required_points,
        optional_points=question.optional_points,
        critical_errors=question.critical_errors,
        final_answer=str(answer["answer"]),
        cited_chunks=tuple(cited_chunks),
    )


def validate_blind_payload(payload: dict[str, Any]) -> None:
    if set(payload) != BLIND_INPUT_KEYS:
        raise JudgeInputError("Judge盲审输入字段偏离冻结白名单")
    chunks = payload.get("cited_chunks")
    if not isinstance(chunks, list) or not chunks:
        raise JudgeInputError("Judge盲审输入必须包含实际引用Chunk")
    for chunk in chunks:
        if not isinstance(chunk, dict) or set(chunk) != BLIND_CHUNK_KEYS:
            raise JudgeInputError("Judge引用Chunk字段偏离冻结白名单")
    serialized = json.dumps(payload, ensure_ascii=False).lower()
    forbidden = (
        '"score"',
        '"rank"',
        '"threshold"',
        '"model"',
        '"classification"',
        '"top_k"',
        '"latency"',
        '"elapsed_seconds"',
    )
    present = [field for field in forbidden if field in serialized]
    if present:
        raise JudgeInputError(f"Judge盲审输入包含禁止字段：{present}")


def prepare_judge_inputs(run_dir: Path) -> dict[str, Any]:
    freeze = validate_h2_freeze()
    question_set = load_h2_question_set(EVALUATION_QUESTIONS_PATH)
    if question_set.sha256 != freeze["evaluation_set"]["sha256"]:
        raise JudgeInputError("正式题集与H2冻结哈希不一致")
    evaluation_summary_path = run_dir / "evaluation" / "summary.json"
    if not evaluation_summary_path.is_file():
        raise FileNotFoundError("缺少正式评价summary.json")
    evaluation_summary = read_json(evaluation_summary_path)
    if evaluation_summary.get("completed_count") != 30:
        raise JudgeInputError("正式30题尚未全部持久化")

    output_dir = run_dir / "judge" / JUDGE_INPUTS_DIR_NAME
    output_dir.mkdir(parents=True, exist_ok=True)
    included: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for question in question_set.questions:
        result_path = (
            run_dir
            / "evaluation"
            / "questions"
            / question.question_id
            / "attempt_001"
            / "result.json"
        )
        result = read_json(result_path)
        if question.scope != "in_scope":
            excluded.append(
                {
                    "question_id": question.question_id,
                    "scope": question.scope,
                    "reason": "refusal_scored_by_program",
                    "final_state": result["final_state"],
                }
            )
            continue
        if result.get("final_state") != "answered":
            excluded.append(
                {
                    "question_id": question.question_id,
                    "scope": question.scope,
                    "reason": "no_valid_answer_to_judge",
                    "final_state": result["final_state"],
                }
            )
            continue
        blind = _blind_input(question, result)
        payload = blind.to_payload()
        validate_blind_payload(payload)
        path = output_dir / f"{question.question_id}.json"
        payload_hash = _input_hash(payload)
        if path.is_file():
            existing = read_json(path)
            if _input_hash(existing) != payload_hash:
                raise JudgeInputError(
                    f"{question.question_id}已有盲审输入与正式结果不一致"
                )
        else:
            write_json_atomic(path, payload)
        included.append(
            {
                "question_id": question.question_id,
                "input_path": (
                    f"judge/{JUDGE_INPUTS_DIR_NAME}/{question.question_id}.json"
                ),
                "input_sha256": payload_hash,
                "citation_count": len(payload["cited_chunks"]),
            }
        )
    manifest = {
        "schema_version": "formal_judge_inputs_manifest_v1",
        "experiment_run_id": run_dir.name,
        "created_at": datetime.now().astimezone().isoformat(),
        "status": "passed",
        "question_set_sha256": question_set.sha256,
        "evaluation_attempt": "attempt_001",
        "blind_field_whitelist": sorted(BLIND_INPUT_KEYS),
        "blind_chunk_field_whitelist": sorted(BLIND_CHUNK_KEYS),
        "input_count": len(included),
        "excluded_count": len(excluded),
        "included": included,
        "excluded": excluded,
        "generation_model_hidden": True,
        "classification_hidden": True,
        "retrieval_scores_hidden": True,
        "unreferenced_top5_hidden": True,
    }
    write_json_atomic(output_dir / "manifest.json", manifest)
    return manifest


def load_blind_input(path: Path) -> BlindJudgeInput:
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise JudgeInputError("Judge盲审输入必须是JSON对象")
    validate_blind_payload(payload)
    chunks = payload["cited_chunks"]
    return BlindJudgeInput(
        question_id=str(payload["question_id"]),
        question=str(payload["question"]),
        required_points=tuple(str(item) for item in payload["required_points"]),
        optional_points=tuple(str(item) for item in payload["optional_points"]),
        critical_errors=tuple(str(item) for item in payload["critical_errors"]),
        final_answer=str(payload["final_answer"]),
        cited_chunks=tuple(
            {
                "chunk_id": str(chunk["chunk_id"]),
                "source_path": str(chunk["source_path"]),
                "section_path": str(chunk["section_path"]),
                "content": str(chunk["content"]),
            }
            for chunk in chunks
        ),
    )
