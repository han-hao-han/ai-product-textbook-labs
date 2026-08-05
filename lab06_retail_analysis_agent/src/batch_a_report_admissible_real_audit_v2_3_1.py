"""Concentrated offline audit of the single V2.3.1 real checkpoint."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "batch_a_report_admissible_v2_3_1_20260804T131120_351077+0800"
RUN_DIR = PROJECT_ROOT / "results" / "raw" / RUN_ID


class RealCheckpointAuditError(ValueError):
    """Raised when saved real evidence does not support the conclusion."""


def _read(name: str) -> dict[str, Any]:
    value = json.loads((RUN_DIR / name).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RealCheckpointAuditError(f"object required: {name}")
    return value


def run_concentrated_audit() -> dict[str, Any]:
    summary = _read("summary.json")
    case = _read("Q02.json")
    transport = _read("transport_audit.json")
    outcome = case["outcome"]
    rejected = outcome["rejected_report_evidence"]
    issues = rejected["report_validation"]["issues"]
    target = next(
        (
            item
            for item in issues
            if item.get("code") == "untraceable_numeric_token"
            and item.get("location") == "sections[4].claims[0]"
            and "：5。" in item.get("message", "")
        ),
        None,
    )
    claims = [
        claim
        for section in rejected["report_draft"]["sections"]
        for claim in section["claims"]
    ]
    recommendation = next(
        claim
        for claim in claims
        if "建议重点关注销售额排名前5" in claim["statement"]
    )
    tool_evidence_claim = next(
        claim for claim in claims if "top_n=5" in claim["statement"]
    )
    fact_one = next(
        fact for fact in outcome["facts"] if fact["fact_id"] == "FACT-001"
    )
    request_audit = transport["requests"]
    if not (
        summary["status"] == "failed_stopped"
        and summary["question_ids_executed"] == ["Q02"]
        and summary["question_ids_not_executed"]
        == ["Q06", "Q08", "Q09", "Q10"]
        and summary["actual_response_attempts"] == 2
        and summary["completed_model_responses"] == 2
        and summary["failed_transport_or_provider_attempts"] == 0
        and summary["automatic_retry_performed"] is False
        and target is not None
        and fact_one["metric"] == "top_n"
        and fact_one["value"] == "5"
        and any(
            item.get("fact_id") == "FACT-001"
            for item in tool_evidence_claim["evidence"]
        )
        and all(
            item.get("fact_id") != "FACT-001"
            for item in recommendation["evidence"]
        )
        and [item["outbound_tool_count"] for item in request_audit] == [7, 0]
        and request_audit[-1]["removed_tool_payload_keys"]
        == ["arguments", "instruction", "result"]
        and transport["request_headers_saved"] is False
        and transport["request_body_saved"] is False
        and transport["authorization_header_value_saved"] is False
    ):
        raise RealCheckpointAuditError(
            "saved evidence does not support the V2.3.1 root cause"
        )
    audit = {
        "schema_version": (
            "1.5.6-h3-batch-a-report-admissible-real-audit-v2.3.1-v1"
        ),
        "run_id": RUN_ID,
        "status": "root_cause_confirmed",
        "real_model": "deepseek-v4-flash",
        "real_response_counts": {
            "attempted": 2,
            "completed": 2,
            "transport_or_provider_failed": 0,
            "automatic_retries": 0,
        },
        "root_failure": {
            "stage": "report_validation",
            "code": "untraceable_numeric_token",
            "unsupported_token": "5",
            "location": "sections[4].claims[0]",
            "claim_contains": "销售额排名前5",
            "claim_evidence_ids": [
                item.get("fact_id") for item in recommendation["evidence"]
            ],
            "required_local_evidence_id": "FACT-001",
            "required_local_evidence_was_available_to_model": True,
            "required_local_evidence_was_cited_elsewhere": True,
            "required_local_evidence_was_missing_from_failed_claim": True,
        },
        "boundary_findings": {
            "report_admissible_projection_worked": True,
            "internal_row_count_leak_recurred": False,
            "terminal_business_tools_hidden": True,
            "terminal_json_serialization_passed": True,
            "claim_local_validator_behaved_as_frozen": True,
            "harness_or_reference_answer_is_root_cause": False,
            "model_claim_evidence_selection_is_root_cause": True,
        },
        "secondary_harness_cascade": {
            "historical_saved_code": "not_all_seven_tools_visible",
            "root_failure_affected": False,
            "cause": (
                "legacy batch runner expected seven visible tools on the "
                "closed terminal step"
            ),
            "offline_fix": (
                "business steps require seven tools; V2.3.1 terminal "
                "requires zero visible tools"
            ),
            "real_response_reclassified_or_repaired": False,
        },
        "batch_stop": {
            "q02_executed": True,
            "later_questions_executed": False,
            "later_question_ids": ["Q06", "Q08", "Q09", "Q10"],
            "automatic_resume_allowed": False,
        },
        "privacy": {
            "api_key_saved": False,
            "authorization_header_value_saved": False,
            "request_headers_saved": False,
            "request_body_saved": False,
        },
        "real_model_called_during_this_audit": False,
    }
    (RUN_DIR / "concentrated_audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return audit


__all__ = ["RealCheckpointAuditError", "run_concentrated_audit"]
