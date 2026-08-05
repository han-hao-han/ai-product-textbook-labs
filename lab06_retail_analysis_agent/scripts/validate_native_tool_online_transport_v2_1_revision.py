"""Offline transport validation for the native-tool online candidate."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.fixed_question_validation import (  # noqa: E402
    load_frozen_questions,
    validate_fixed_question,
)
from src.mock_h2_registry import FrozenH2MockRegistry  # noqa: E402
from src.mock_native_tool_client_v2_1_revision import (  # noqa: E402
    FrozenQuestionNativeToolMockClient,
)
from src.native_tool_transport_mock_v2_1_revision import (  # noqa: E402
    OfflineNativeToolTransportV2_1Revision,
)
from src.online_native_tool_candidate_v2_1_revision import (  # noqa: E402
    NativeToolOnlineCandidateV2_1Revision,
)


ACCEPTED_OFFLINE_HARNESS_STATUSES = {
    "protocol_and_dataflow_passed",
    "passed_deterministic_pending_manual_review",
}


def validate_request_contract(
    requests: list[Any],
    *,
    q06_terminal_request_index: int,
) -> bool:
    """Validate the frozen Q06 terminal exception and all normal requests."""
    for request in requests:
        common = (
            request.url == "https://api.deepseek.com/beta/chat/completions"
            and request.tool_count == 7
            and request.all_tools_strict
            and request.all_parameters_closed
        )
        if not common:
            return False
        if request.request_index == q06_terminal_request_index:
            if not (
                request.tool_choice == "none"
                and request.response_format_present
                and request.response_format == {"type": "json_object"}
            ):
                return False
        elif not (
            request.tool_choice == "auto"
            and not request.response_format_present
            and request.response_format is None
        ):
            return False
    return True


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    timestamp = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S_%f%z")
    run_id = f"native_tool_transport_v2_1_revision_{timestamp}"
    output_dir = PROJECT_ROOT / "results" / "raw" / run_id
    result_root = f"results/raw/{run_id}"
    placeholder_secret = "offline-transport-placeholder-not-real"
    questions = load_frozen_questions()
    transport = OfflineNativeToolTransportV2_1Revision(
        FrozenQuestionNativeToolMockClient()
    )
    candidate = NativeToolOnlineCandidateV2_1Revision(
        api_key=placeholder_secret,
        registry=FrozenH2MockRegistry(),
        response_limit=20,
        transport=transport,
        question_count=10,
    )

    passed = 0
    tool_calls = 0
    facts = 0
    charts = 0
    case_records: list[dict[str, Any]] = []
    for index in range(1, 11):
        question_id = f"Q{index:02d}"
        request_start = len(transport.requests)
        outcome = candidate.run_turn(
            session_id="SESSION-native-transport-audit",
            turn_id=f"TURN-{index:03d}",
            question=questions[question_id]["question"],
            result_root=result_root,
        )
        validation = validate_fixed_question(question_id, outcome)
        request_end = len(transport.requests)
        record = {
            "question_id": question_id,
            "status": outcome.status,
            "fixed_answer_validation": validation.model_dump(mode="json"),
            "model_response_count": outcome.model_response_count,
            "tool_sequence": [
                call.tool_name for call in outcome.tool_calls
            ],
            "tool_arguments": [
                call.arguments for call in outcome.tool_calls
            ],
            "fact_count": len(outcome.facts),
            "chart_count": len(outcome.charts),
            "report_validation_status": (
                None
                if outcome.report_validation is None
                else outcome.report_validation.status
            ),
            "transport_request_indexes": list(
                range(request_start + 1, request_end + 1)
            ),
            "transport_tool_result_message_counts": [
                request.tool_result_message_count
                for request in transport.requests[
                    request_start:request_end
                ]
            ],
            "native_model_trace": [
                {
                    "response_index": step.response_index,
                    "visible_tool_count": len(step.visible_tool_names),
                    "visible_tool_names": list(step.visible_tool_names),
                    "selected_tool_name": step.selected_tool_name,
                    "selected_arguments": step.selected_arguments,
                    "normalized_arguments": step.normalized_arguments,
                    "tool_result_messages_seen": (
                        step.tool_result_messages_seen
                    ),
                    "requested_tool_choice": step.requested_tool_choice,
                }
                for step in candidate.last_trace
            ],
        }
        _write_json(output_dir / f"{question_id}.json", record)
        case_records.append(record)
        passed += validation.status in ACCEPTED_OFFLINE_HARNESS_STATUSES
        tool_calls += len(outcome.tool_calls)
        facts += len(outcome.facts)
        charts += len(outcome.charts)

    transport_audit = transport.audit_payload()
    _write_json(output_dir / "transport_audit.json", transport_audit)

    limit_transport = OfflineNativeToolTransportV2_1Revision(
        FrozenQuestionNativeToolMockClient()
    )
    limit_candidate = NativeToolOnlineCandidateV2_1Revision(
        api_key="offline-limit-probe",
        registry=FrozenH2MockRegistry(),
        response_limit=1,
        transport=limit_transport,
    )
    limit_outcome = limit_candidate.run_turn(
        session_id="SESSION-native-limit-probe",
        turn_id="TURN-001",
        question=questions["Q01"]["question"],
        result_root=result_root,
    )
    limit_probe = {
        "status": limit_outcome.status,
        "error_stage": limit_outcome.error_stage,
        "tool_calls_completed_before_stop": len(limit_outcome.tool_calls),
        "transport_requests": len(limit_transport.requests),
        "snapshot": {
            "limit": limit_candidate.response_limit_snapshot().limit,
            "attempted": limit_candidate.response_limit_snapshot().attempted,
            "completed": limit_candidate.response_limit_snapshot().completed,
            "failed": limit_candidate.response_limit_snapshot().failed,
        },
        "stopped_before_second_transport": (
            len(limit_transport.requests) == 1
            and limit_candidate.response_limit_snapshot().attempted == 1
        ),
    }
    _write_json(output_dir / "response_limit_probe.json", limit_probe)

    audit_text = json.dumps(transport_audit, ensure_ascii=False)
    q06 = case_records[5]
    q06_terminal_request_index = q06["transport_request_indexes"][-1]
    request_contract_passed = validate_request_contract(
        transport.requests,
        q06_terminal_request_index=q06_terminal_request_index,
    )
    snapshot = candidate.response_limit_snapshot()
    summary = {
        "schema_version": (
            "1.5.6-h3-native-tool-online-transport-validation-v1"
        ),
        "stage": "native_tool_online_candidate_offline_transport",
        "status": (
            "passed"
            if passed == 10
            and request_contract_passed
            and snapshot.attempted == 20
            and snapshot.completed == 20
            and q06["transport_tool_result_message_counts"] == [0, 1, 2]
            and limit_probe["stopped_before_second_transport"]
            and placeholder_secret not in audit_text
            else "failed"
        ),
        "real_network_opened": False,
        "real_model_called": False,
        "api_key_read_from_environment": False,
        "recipe_router_used": False,
        "standard_json_gate_used": True,
        "fixed_questions_passed": passed,
        "fixed_questions_total": 10,
        "request_count": len(transport.requests),
        "beta_strict_tool_request_count": len(transport.requests),
        "seven_tool_request_count": sum(
            request.tool_count == 7 for request in transport.requests
        ),
        "tool_call_count": tool_calls,
        "fact_count": facts,
        "chart_count": charts,
        "response_limit": {
            "limit": snapshot.limit,
            "attempted": snapshot.attempted,
            "completed": snapshot.completed,
            "failed": snapshot.failed,
        },
        "request_contract_passed": request_contract_passed,
        "request_contract_counts": {
            "auto_without_response_format": sum(
                request.tool_choice == "auto"
                and not request.response_format_present
                for request in transport.requests
            ),
            "q06_none_with_json_object": sum(
                request.request_index == q06_terminal_request_index
                and request.tool_choice == "none"
                and request.response_format == {"type": "json_object"}
                for request in transport.requests
            ),
        },
        "q06_request_progression": {
            "request_indexes": q06["transport_request_indexes"],
            "terminal_request_index": q06_terminal_request_index,
            "tool_result_message_counts": q06[
                "transport_tool_result_message_counts"
            ],
            "tool_sequence": q06["tool_sequence"],
            "second_call_start_date": q06["tool_arguments"][1][
                "start_date"
            ],
            "second_call_end_date": q06["tool_arguments"][1][
                "end_date"
            ],
        },
        "response_limit_probe": limit_probe,
        "privacy_audit": {
            "placeholder_secret_saved": placeholder_secret in audit_text,
            "authorization_value_saved": False,
            "request_body_saved": False,
            "raw_customer_id_exported": False,
        },
    }
    _write_json(output_dir / "summary.json", summary)
    print(
        json.dumps(
            {**summary, "run_id": run_id, "output_dir": str(output_dir)},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
