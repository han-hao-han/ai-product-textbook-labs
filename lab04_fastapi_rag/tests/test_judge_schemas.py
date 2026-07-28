from __future__ import annotations

import json

import pytest

from src.judge_schemas import parse_judge_output


REQUIRED = ("要点A", "要点B")
CRITICAL = ("关键错误A",)


def _payload() -> dict[str, object]:
    return {
        "answer_grade": "fully_correct",
        "covered_required_points": ["要点A", "要点B"],
        "missing_required_points": [],
        "critical_errors": [],
        "unsupported_major_claim": False,
        "citation_supports_answer": True,
        "citation_set_minimal": True,
        "review_reason": "全部必答点均有引用支持。",
    }


def test_parse_judge_output_accepts_exact_partition() -> None:
    result = parse_judge_output(
        json.dumps(_payload(), ensure_ascii=False),
        required_points=REQUIRED,
        allowed_critical_errors=CRITICAL,
    )
    assert result.answer_grade.value == "fully_correct"


def test_parse_judge_output_rejects_rewritten_required_point() -> None:
    payload = _payload()
    payload["covered_required_points"] = ["改写的要点A", "要点B"]
    with pytest.raises(ValueError, match="精确划分"):
        parse_judge_output(
            json.dumps(payload, ensure_ascii=False),
            required_points=REQUIRED,
            allowed_critical_errors=CRITICAL,
        )


def test_parse_judge_output_rejects_inconsistent_fully_correct() -> None:
    payload = _payload()
    payload["answer_grade"] = "fully_correct"
    payload["covered_required_points"] = ["要点A"]
    payload["missing_required_points"] = ["要点B"]
    with pytest.raises(ValueError, match="fully_correct"):
        parse_judge_output(
            json.dumps(payload, ensure_ascii=False),
            required_points=REQUIRED,
            allowed_critical_errors=CRITICAL,
        )


def test_parse_judge_output_rejects_duplicate_required_point() -> None:
    payload = _payload()
    payload["covered_required_points"] = ["要点A", "要点A", "要点B"]
    with pytest.raises(ValueError, match="重复项"):
        parse_judge_output(
            json.dumps(payload, ensure_ascii=False),
            required_points=REQUIRED,
            allowed_critical_errors=CRITICAL,
        )
