"""Validate the V2.2.3 Q06 report-revision feedback design offline."""

from __future__ import annotations

import json
import sys
from collections import Counter
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.q06_report_revision_feedback_boundary_v2_2_3 import (  # noqa: E402
    Q06ReportRevisionFeedbackBoundaryError,
    load_q06_report_revision_feedback_contract,
    replay_saved_q06_feedback_design,
    validate_q06_report_revision_feedback_contract,
)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _probe(mutator: Callable[[dict[str, Any]], None]) -> bool:
    changed = deepcopy(load_q06_report_revision_feedback_contract())
    mutator(changed)
    try:
        validate_q06_report_revision_feedback_contract(changed)
    except Q06ReportRevisionFeedbackBoundaryError:
        return True
    return False


def main() -> int:
    contract = validate_q06_report_revision_feedback_contract()
    replay = replay_saved_q06_feedback_design()
    feedback = replay.feedback.model_dump(mode="json")
    issue_counts = Counter(item["code"] for item in feedback["issues"])
    probes = {
        "activate_before_freeze_rejected": _probe(
            lambda value: value["candidate_revision_protocol"].update(
                {"active": True}
            )
        ),
        "second_revision_response_rejected": _probe(
            lambda value: value["candidate_revision_protocol"].update(
                {"maximum_report_revision_responses": 2}
            )
        ),
        "fifth_total_response_rejected": _probe(
            lambda value: value["candidate_revision_protocol"].update(
                {"maximum_total_model_responses_if_future_authorized": 5}
            )
        ),
        "automatic_retry_rejected": _probe(
            lambda value: value["candidate_revision_protocol"].update(
                {"automatic_retry_count": 1}
            )
        ),
        "revision_tool_call_rejected": _probe(
            lambda value: value["candidate_revision_protocol"].update(
                {"tool_calls_allowed_in_revision_response": True}
            )
        ),
        "real_call_authority_rejected": _probe(
            lambda value: value["scope"].update(
                {"real_model_calls_allowed": True}
            )
        ),
        "program_fact_selection_rejected": _probe(
            lambda value: value["deterministic_feedback_candidate"][
                "exclude_fields"
            ].remove("candidate_fact_ids_selected_by_program")
        ),
        "manual_flags_as_feedback_rejected": _probe(
            lambda value: value["deterministic_feedback_candidate"][
                "exclude_fields"
            ].remove("manual_review_flags")
        ),
        "hard_stop_weakening_rejected": _probe(
            lambda value: value["deterministic_feedback_candidate"].update(
                {"hard_stop_issue_codes": ["duplicate_fact_id"]}
            )
        ),
    }
    expected_counts = {
        "untraceable_numeric_token": 1,
        "unsupported_significance_claim": 1,
        "unsupported_quantity_superlative": 1,
        "unsupported_order_superlative": 1,
        "unsupported_average_value_claim": 2,
        "unsupported_product_classification": 2,
    }
    serialized_feedback = json.dumps(feedback, ensure_ascii=False)
    privacy_audit = {
        "api_key_present": "Bearer " in serialized_feedback,
        "authorization_header_present": (
            '"Authorization"' in serialized_feedback
        ),
        "raw_customer_id_present": (
            '"customer_id"' in serialized_feedback.lower()
            or '"customerid"' in serialized_feedback.lower()
        ),
        "raw_provider_response_duplicated": False,
        "program_selected_fact_ids_present": "FACT-" in serialized_feedback,
        "replacement_statement_present": (
            "replacement_statement" in serialized_feedback
        ),
    }
    passed = (
        contract["status"]
        in {
            "offline_design_pending_validation_and_user_freeze",
            "offline_validated_pending_user_freeze",
        }
        and replay.formal_validation_status == "failed"
        and replay.formal_issue_count == 8
        and replay.manual_review_flag_count == 8
        and len(feedback["issues"]) == 8
        and dict(issue_counts) == expected_counts
        and replay.fact_count == 48
        and replay.source_response_unchanged
        and all(probes.values())
        and not any(privacy_audit.values())
    )
    timestamp = datetime.now().astimezone().strftime(
        "%Y%m%dT%H%M%S_%f%z"
    )
    run_id = f"q06_report_revision_feedback_v2_2_3_offline_{timestamp}"
    output_dir = PROJECT_ROOT / "results" / "raw" / run_id
    summary = {
        "schema_version": (
            "1.5.6-h3-q06-report-revision-feedback-v2.2.3-offline-v1"
        ),
        "run_id": run_id,
        "status": "passed" if passed else "failed",
        "stage": "q06_report_revision_feedback_boundary_v2_2_3",
        "source_run_id": (
            "q06_v2_2_1_flash_real_revalidation_"
            "20260803T153719_794668+0800"
        ),
        "source_sha256": replay.source_sha256,
        "source_response_unchanged": replay.source_response_unchanged,
        "formal_validation_status": replay.formal_validation_status,
        "formal_issue_count": replay.formal_issue_count,
        "formal_issue_counts": dict(issue_counts),
        "manual_review_flag_count_excluded_from_feedback": (
            replay.manual_review_flag_count
        ),
        "fact_count_unchanged": replay.fact_count,
        "feedback_issue_count": len(feedback["issues"]),
        "feedback_sha256": replay.feedback_sha256,
        "feedback_payload": feedback,
        "negative_probes": probes,
        "candidate_protocol": {
            "active": False,
            "existing_response_cap": 3,
            "future_candidate_response_cap": 4,
            "maximum_report_revision_responses": 1,
            "automatic_retry_count": 0,
            "tool_choice": "none",
            "response_format": {"type": "json_object"},
            "real_call_authorized": False,
        },
        "privacy_audit": privacy_audit,
        "prompt_changed": False,
        "model_control_schema_changed": False,
        "fact_or_tool_changed": False,
        "orchestrator_changed": False,
        "real_network_opened": False,
        "real_model_called": False,
        "api_key_read_from_environment": False,
        "candidate_result": "feedback_ready_revision_not_executed",
    }
    _write_json(output_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
