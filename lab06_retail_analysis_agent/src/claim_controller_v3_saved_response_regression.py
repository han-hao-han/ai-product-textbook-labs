"""Replay the saved V20 Q01 failure as a V3 structural regression check."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class SavedResponseRegressionError(ValueError):
    pass


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SavedResponseRegressionError(f"saved response is not an object: {path.name}")
    return value


def validate_v20_q01_to_v3_regression(
    *, old_failure_path: Path, v3_case_path: Path
) -> dict[str, Any]:
    """Prove the old missing-period failure is mandatory and covered in V3."""
    old = _load(old_failure_path)
    current = _load(v3_case_path)
    old_codes = old.get("root_failure_codes", [])
    if old.get("question_id") != "Q01" or "deterministic_report_validation_failed" not in old_codes:
        raise SavedResponseRegressionError("saved V20 input is not the frozen Q01 root failure")
    traces = current.get("terminal_protocol_trace", [])
    if current.get("question_id") != "Q01" or not traces or traces[-1].get("status") != "passed":
        raise SavedResponseRegressionError("V3 saved response is not a passed Q01 terminal trace")
    trace = traces[-1]
    plan = trace.get("model_visible_claim_plan", {})
    result_claims = [
        item for item in plan.get("claims", []) if item.get("slot_id") == "SLOT-002"
    ]
    required = any("2011-12" in item.get("required_literals", []) for item in result_claims)
    mapped_sections = trace.get("mapped_program_response", {}).get("report", {}).get("sections", [])
    fact_bound = any(
        reference.get("fact_id") == "FACT-007"
        for section in mapped_sections
        for claim in section.get("claims", [])
        for reference in claim.get("evidence", [])
    )
    fixed_status = current.get("new_harness_validation", {}).get("status")
    passed = required and fact_bound and fixed_status == "passed_deterministic_pending_manual_review"
    return {
        "schema_version": "1.5.6-h3-claim-controller-v3-saved-response-regression-v1",
        "status": "passed" if passed else "failed",
        "source_question_id": "Q01",
        "old_root_failure_codes": old_codes,
        "v3_required_literal_2011_12": required,
        "v3_program_bound_fact_007": fact_bound,
        "v3_harness_status": fixed_status,
        "real_model_called": False,
    }


__all__ = ["SavedResponseRegressionError", "validate_v20_q01_to_v3_regression"]
