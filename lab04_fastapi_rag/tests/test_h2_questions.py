from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.h2_questions import (
    audit_h2_question_sets,
    load_gate_policy,
    load_h2_question_set,
)
from src.h2_review import render_h2_candidate_review
from src.paths import (
    CALIBRATION_QUESTIONS_PATH,
    EVALUATION_QUESTIONS_PATH,
    RETRIEVAL_GATE_POLICY_PATH,
)


def _referenced_paths(*question_sets) -> set[str]:
    paths: set[str] = set()
    for question_set in question_sets:
        for item in question_set.questions:
            for group in item.acceptable_source_groups:
                paths.update(group.paths)
            paths.update(item.related_corpus_paths)
    return paths


def test_h2_candidate_sets_match_all_frozen_quotas() -> None:
    calibration = load_h2_question_set(CALIBRATION_QUESTIONS_PATH)
    evaluation = load_h2_question_set(EVALUATION_QUESTIONS_PATH)
    gate_policy = load_gate_policy(RETRIEVAL_GATE_POLICY_PATH)

    audit = audit_h2_question_sets(
        calibration,
        evaluation,
        gate_policy,
        included_paths=_referenced_paths(calibration, evaluation),
        source_commit=calibration.source_commit,
        corpus_sha256=calibration.corpus_sha256,
    )

    assert audit["calibration"]["scope_counts"] == {
        "boundary": 10,
        "in_scope": 20,
        "out_of_scope": 20,
    }
    assert audit["evaluation"]["scope_counts"] == {
        "boundary": 6,
        "in_scope": 18,
        "out_of_scope": 6,
    }
    assert audit["evaluation"]["document_group_counts"] == {
        "advanced": 4,
        "deployment": 3,
        "how-to": 2,
        "tutorial": 9,
    }
    assert audit["evaluation"]["question_type_counts"] == {
        "code_example": 5,
        "comprehensive": 4,
        "concise_concept": 4,
        "procedure": 5,
    }
    assert audit["evaluation"]["questions_with_short_python_code"] == 5
    assert audit["gate_policy"]["threshold"] is None


def test_h2_audit_rejects_formal_group_quota_drift(
    tmp_path: Path,
) -> None:
    payload = json.loads(
        EVALUATION_QUESTIONS_PATH.read_text(encoding="utf-8")
    )
    payload["questions"][0]["document_group"] = "advanced"
    changed_path = tmp_path / "evaluation.json"
    changed_path.write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )
    calibration = load_h2_question_set(CALIBRATION_QUESTIONS_PATH)
    evaluation = load_h2_question_set(changed_path)
    gate_policy = load_gate_policy(RETRIEVAL_GATE_POLICY_PATH)

    with pytest.raises(ValueError, match="文档组配额"):
        audit_h2_question_sets(
            calibration,
            evaluation,
            gate_policy,
            included_paths=_referenced_paths(calibration, evaluation),
            source_commit=calibration.source_commit,
            corpus_sha256=calibration.corpus_sha256,
        )


def test_h2_audit_rejects_unknown_source_path() -> None:
    calibration = load_h2_question_set(CALIBRATION_QUESTIONS_PATH)
    evaluation = load_h2_question_set(EVALUATION_QUESTIONS_PATH)
    gate_policy = load_gate_policy(RETRIEVAL_GATE_POLICY_PATH)

    with pytest.raises(ValueError, match="未纳入语料"):
        audit_h2_question_sets(
            calibration,
            evaluation,
            gate_policy,
            included_paths=set(),
            source_commit=calibration.source_commit,
            corpus_sha256=calibration.corpus_sha256,
        )


def test_gate_policy_rejects_prefilled_threshold(tmp_path: Path) -> None:
    payload = json.loads(
        RETRIEVAL_GATE_POLICY_PATH.read_text(encoding="utf-8")
    )
    payload["threshold"] = 0.5
    path = tmp_path / "gate.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="不得预填"):
        load_gate_policy(path)


def test_h2_review_contains_every_question_but_no_scores() -> None:
    calibration = load_h2_question_set(CALIBRATION_QUESTIONS_PATH)
    evaluation = load_h2_question_set(EVALUATION_QUESTIONS_PATH)
    gate_policy = load_gate_policy(RETRIEVAL_GATE_POLICY_PATH)
    audit = audit_h2_question_sets(
        calibration,
        evaluation,
        gate_policy,
        included_paths=_referenced_paths(calibration, evaluation),
        source_commit=calibration.source_commit,
        corpus_sha256=calibration.corpus_sha256,
    )

    markdown = render_h2_candidate_review(
        calibration,
        evaluation,
        gate_policy,
        audit,
    )

    assert "CAL_IN_001" in markdown
    assert "EVAL_OUT_006" in markdown
    assert "candidate_pending_h2_confirmation" in markdown
    assert "正式阈值：" not in markdown
