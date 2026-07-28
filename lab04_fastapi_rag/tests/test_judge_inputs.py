from __future__ import annotations

import pytest

from src.judge_inputs import JudgeInputError, validate_blind_payload


def _payload() -> dict[str, object]:
    return {
        "question_id": "Q1",
        "question": "问题",
        "required_points": ["要点"],
        "optional_points": [],
        "critical_errors": ["错误"],
        "final_answer": "答案",
        "cited_chunks": [
            {
                "chunk_id": "c1",
                "source_path": "docs/a.md",
                "section_path": "章节",
                "content": "证据",
            }
        ],
    }


def test_validate_blind_payload_accepts_exact_whitelist() -> None:
    validate_blind_payload(_payload())


@pytest.mark.parametrize(
    "forbidden_key",
    ["score", "rank", "threshold", "model", "classification", "top_k"],
)
def test_validate_blind_payload_rejects_forbidden_field(
    forbidden_key: str,
) -> None:
    payload = _payload()
    payload[forbidden_key] = "leak"
    with pytest.raises(JudgeInputError, match="白名单"):
        validate_blind_payload(payload)


def test_validate_blind_payload_rejects_chunk_score() -> None:
    payload = _payload()
    payload["cited_chunks"][0]["score"] = 0.9  # type: ignore[index]
    with pytest.raises(JudgeInputError, match="引用Chunk字段"):
        validate_blind_payload(payload)
