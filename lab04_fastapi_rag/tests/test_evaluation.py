from __future__ import annotations

from src.evaluation import compare_formal_result
from src.h2_questions import H2Question, SourceGroup


def _question(
    *,
    scope: str = "in_scope",
    question_type: str = "procedure",
) -> H2Question:
    return H2Question(
        question_id="Q1",
        scope=scope,
        question_type=(
            question_type if scope == "in_scope" else "not_applicable"
        ),
        document_group="tutorial" if scope == "in_scope" else None,
        question="问题",
        required_points=("要点",),
        optional_points=(),
        critical_errors=("错误",),
        acceptable_source_groups=(
            (SourceGroup("g1", ("docs/a.md",)),)
            if scope == "in_scope"
            else ()
        ),
        related_corpus_paths=(),
        expected_behavior="answered" if scope == "in_scope" else "refused",
        contains_short_python_code=False,
    )


def _result(
    *,
    final_state: str = "answered",
    source_paths: tuple[str, ...] = (
        "docs/a.md",
        "docs/b.md",
        "docs/c.md",
        "docs/d.md",
        "docs/e.md",
    ),
    classification: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "final_state": final_state,
        "classification": classification,
        "retrieval": {
            "hits": [
                {"source_path": path, "chunk_id": f"c{index}"}
                for index, path in enumerate(source_paths, start=1)
            ]
        },
    }


def test_compare_formal_result_scores_retrieval_and_classification() -> None:
    comparison = compare_formal_result(
        _question(),
        _result(
            classification={
                "question_type": "procedure",
                "fallback": False,
            }
        ),
    )
    assert comparison["retrieval"]["top1_reasonable_hit"] is True
    assert comparison["retrieval"]["top5_source_status"] == "full"
    assert comparison["classification"]["strict_correct"] is True
    assert comparison["classification"]["acceptable_correct"] is True


def test_classification_fallback_is_acceptable_only_for_matching_label() -> None:
    comparison = compare_formal_result(
        _question(question_type="comprehensive"),
        _result(
            classification={
                "question_type": "comprehensive",
                "fallback": True,
            }
        ),
    )
    assert comparison["classification"]["strict_correct"] is False
    assert comparison["classification"]["acceptable_correct"] is True
    assert comparison["classification"]["classification_failed"] is True


def test_boundary_refusal_separates_correctness_and_mechanism() -> None:
    comparison = compare_formal_result(
        _question(scope="boundary"),
        _result(final_state="retrieval_rejected"),
    )
    assert comparison["refusal"]["refusal_correct"] is True
    assert comparison["refusal"]["mechanism_conforming"] is False
    assert comparison["refusal"]["expected_mechanism"] == "model_refused"


def test_out_of_scope_retrieval_rejection_conforms() -> None:
    comparison = compare_formal_result(
        _question(scope="out_of_scope"),
        _result(final_state="retrieval_rejected"),
    )
    assert comparison["refusal"]["refusal_correct"] is True
    assert comparison["refusal"]["mechanism_conforming"] is True
