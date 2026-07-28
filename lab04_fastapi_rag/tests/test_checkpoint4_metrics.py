from __future__ import annotations

from types import SimpleNamespace

from src.checkpoint4_report import (
    _answer_metrics,
    _classification_metrics,
    _refusal_metrics,
    _retrieval_metrics,
)


def _record(
    scope: str,
    *,
    top1: bool = True,
    top5: str = "full",
    strict: bool = True,
    acceptable: bool = True,
    failed: bool = False,
    refusal: bool = True,
    mechanism: bool = True,
) -> dict[str, object]:
    return {
        "question": SimpleNamespace(scope=scope),
        "comparison": {
            "retrieval": {
                "single_source": scope == "in_scope",
                "top1_reasonable_hit": top1 if scope == "in_scope" else None,
                "top5_source_status": (
                    top5 if scope == "in_scope" else "not_applicable"
                ),
            },
            "classification": {
                "strict_correct": strict,
                "acceptable_correct": acceptable,
                "classification_failed": failed,
            },
            "refusal": {
                "refusal_correct": refusal,
                "mechanism_conforming": mechanism,
            },
        },
    }


def test_metrics_keep_partial_as_aggregate_failure() -> None:
    records = [
        _record("in_scope", top5="full"),
        _record("in_scope", top1=False, top5="partial"),
    ]
    retrieval = _retrieval_metrics(records)
    assert retrieval["top1_reasonable_hit_rate"] == 0.5
    assert retrieval["top5_source_hit_rate"] == 0.5
    assert retrieval["top5_partial_hits"] == 1


def test_answer_rate_uses_all_in_scope_questions_as_denominator() -> None:
    records = [_record("in_scope") for _ in range(3)]
    judge = {
        "records": [
            {"answer_grade": "fully_correct"},
            {"answer_grade": "mostly_correct"},
        ]
    }
    metrics = _answer_metrics(records, judge)
    assert metrics["fully_correct_rate"] == 1 / 3
    assert metrics["acceptable_answer_rate"] == 2 / 3
    assert metrics["not_judged_or_no_valid_answer_count"] == 1


def test_classification_and_refusal_metrics_are_scope_separated() -> None:
    records = [
        _record("in_scope", strict=False, acceptable=True, failed=True),
        _record("boundary", refusal=True, mechanism=False),
    ]
    classification = _classification_metrics(records)
    boundary = _refusal_metrics(records, "boundary")
    assert classification["strict_accuracy"] == 0
    assert classification["acceptable_accuracy"] == 1
    assert classification["failure_count"] == 1
    assert boundary["refusal_accuracy"] == 1
    assert boundary["mechanism_conformity_rate"] == 0
