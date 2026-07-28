from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.gate_calibration import (
    candidate_thresholds,
    evaluate_threshold,
    select_threshold,
    validate_h2_freeze,
)
from src.io_utils import sha256_file
from src.paths import (
    CALIBRATION_QUESTIONS_PATH,
    EVALUATION_QUESTIONS_PATH,
    H2_FREEZE_PATH,
    RETRIEVAL_GATE_POLICY_PATH,
)


def test_h2_freeze_matches_confirmed_bytes() -> None:
    freeze = validate_h2_freeze()

    assert sha256_file(CALIBRATION_QUESTIONS_PATH) == (
        "13ccbdd23ac50edeb1e106ea68d295f185cfea6e4d3789db3dd66a2429253d9b"
    )
    assert sha256_file(EVALUATION_QUESTIONS_PATH) == (
        "fd852bcbfd4dfdd91f6b48bdc92d062e905d47f19c1562c79c736e3542155254"
    )
    assert sha256_file(RETRIEVAL_GATE_POLICY_PATH) == (
        "a457b31c53091fd3b16df2eeea1e6ba9e7fc36c1ed17687a87063920bb340769"
    )
    assert freeze["status"] == "h2_frozen_user_confirmed"


def test_candidate_thresholds_cover_all_decision_partitions() -> None:
    values = candidate_thresholds([0.2, 0.4, 0.4, 0.8])

    assert len(values) == 4
    assert values[0] < 0.2
    assert values[1] == pytest.approx(0.3)
    assert values[2] == pytest.approx(0.6)
    assert values[3] > 0.8


def test_select_threshold_obeys_recall_constraint_then_rejection() -> None:
    scores = [0.9, 0.8, 0.7, 0.6]
    scopes = ["in_scope", "in_scope", "boundary", "out_of_scope"]

    selected, metrics, reason = select_threshold(scores, scopes, 0.5)

    assert selected.threshold == pytest.approx(0.75)
    assert selected.in_scope_recall == 1.0
    assert selected.negative_rejection_rate == 1.0
    assert len(metrics) == 5
    assert "满足库内召回率" in reason


def test_select_threshold_uses_fallback_when_constraint_is_impossible() -> None:
    scores = [0.1, 0.9]
    scopes = ["in_scope", "boundary"]

    selected, _, reason = select_threshold(scores, scopes, 1.1)

    assert selected.balanced_accuracy == pytest.approx(0.5)
    assert selected.in_scope_recall == 1.0
    assert "回退规则" in reason


def test_evaluate_threshold_treats_boundary_and_out_as_negative() -> None:
    result = evaluate_threshold(
        [0.9, 0.4, 0.3],
        ["in_scope", "boundary", "out_of_scope"],
        0.5,
        0.9,
    )

    assert result.true_positive == 1
    assert result.true_negative == 2
    assert result.false_positive == 0
    assert result.false_negative == 0


def test_freeze_rejects_evaluation_hash_drift(tmp_path: Path) -> None:
    payload = json.loads(H2_FREEZE_PATH.read_text(encoding="utf-8"))
    payload["evaluation_set"]["sha256"] = "0" * 64
    changed_freeze = tmp_path / "h2_freeze.json"
    changed_freeze.write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="正式集SHA-256"):
        validate_h2_freeze(freeze_path=changed_freeze)


def test_freeze_manifest_contains_no_threshold() -> None:
    payload = json.loads(H2_FREEZE_PATH.read_text(encoding="utf-8"))

    assert "threshold" not in payload
