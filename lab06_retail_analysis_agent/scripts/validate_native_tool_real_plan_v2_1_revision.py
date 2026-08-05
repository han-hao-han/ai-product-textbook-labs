"""Offline plan and injected-transport preflight for five real responses."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path


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
from src.native_tool_real_validation_plan_v2_1_revision import (  # noqa: E402
    PLAN_PATH,
    validate_native_tool_real_validation_plan,
)
from src.native_tool_transport_mock_v2_1_revision import (  # noqa: E402
    OfflineNativeToolTransportV2_1Revision,
)
from src.online_native_tool_candidate_v2_1_revision import (  # noqa: E402
    NativeToolOnlineCandidateV2_1Revision,
)


def main() -> int:
    preflight = validate_native_tool_real_validation_plan()
    timestamp = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S_%f%z")
    run_id = f"native_tool_real_plan_preflight_{timestamp}"
    output_dir = PROJECT_ROOT / "results" / "raw" / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    transport = OfflineNativeToolTransportV2_1Revision(
        FrozenQuestionNativeToolMockClient()
    )
    candidate = NativeToolOnlineCandidateV2_1Revision(
        api_key="offline-plan-preflight-placeholder",
        registry=FrozenH2MockRegistry(),
        response_limit=preflight.response_attempt_upper_bound,
        transport=transport,
        question_count=len(preflight.question_ids),
    )
    questions = load_frozen_questions()
    cases = []
    all_passed = True
    for index, question_id in enumerate(preflight.question_ids, start=1):
        request_start = len(transport.requests)
        outcome = candidate.run_turn(
            session_id="SESSION-native-real-plan-preflight",
            turn_id=f"TURN-{index:03d}",
            question=questions[question_id]["question"],
            result_root=f"results/raw/{run_id}",
        )
        validation = validate_fixed_question(question_id, outcome)
        request_end = len(transport.requests)
        case = {
            "question_id": question_id,
            "status": outcome.status,
            "validation_status": validation.status,
            "response_attempts": request_end - request_start,
            "request_indexes": list(range(request_start + 1, request_end + 1)),
            "tool_result_message_counts": [
                request.tool_result_message_count
                for request in transport.requests[request_start:request_end]
            ],
            "tool_sequence": [call.tool_name for call in outcome.tool_calls],
            "tool_arguments": [call.arguments for call in outcome.tool_calls],
            "fact_count": len(outcome.facts),
            "chart_count": len(outcome.charts),
            "report_validation_status": (
                None
                if outcome.report_validation is None
                else outcome.report_validation.status
            ),
            "manual_review_items": validation.manual_review_items,
        }
        cases.append(case)
        all_passed = all_passed and validation.status == "passed"

    snapshot = candidate.response_limit_snapshot()
    request_contract_passed = all(
        request.tool_count == 7
        and request.all_tools_strict
        and request.all_parameters_closed
        and request.tool_choice == "auto"
        and not request.response_format_present
        for request in transport.requests
    )
    summary = {
        "schema_version": (
            "1.5.6-h3-native-tool-real-plan-offline-preflight-v1"
        ),
        "run_id": run_id,
        "execution_mode": "offline_plan_and_injected_transport_preflight",
        "plan_path": str(PLAN_PATH.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "status": (
            "passed"
            if preflight.status == "passed"
            and all_passed
            and request_contract_passed
            and snapshot.attempted == 5
            and snapshot.completed == 5
            and len(transport.requests) == 5
            else "failed"
        ),
        "real_network_opened": False,
        "api_key_read": False,
        "real_model_called": False,
        "real_model_calls_allowed": False,
        "runner_implemented": False,
        "question_ids": list(preflight.question_ids),
        "response_attempt_upper_bound": preflight.response_attempt_upper_bound,
        "expected_beta_requests": preflight.expected_beta_requests,
        "expected_standard_json_requests": (
            preflight.expected_standard_json_requests
        ),
        "actual_beta_requests": len(transport.requests),
        "actual_standard_json_requests": 0,
        "automatic_retry_count": preflight.automatic_retry_count,
        "stop_on_first_case_failure": preflight.stop_on_first_case_failure,
        "request_contract_passed": request_contract_passed,
        "response_limit_snapshot": {
            "limit": snapshot.limit,
            "attempted": snapshot.attempted,
            "completed": snapshot.completed,
            "failed": snapshot.failed,
        },
        "cases": cases,
        "checks": list(preflight.checks),
        "next_gate": (
            "user freezes plan; freeze does not authorize real model calls"
        ),
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({**summary, "output_dir": str(output_dir)}, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
