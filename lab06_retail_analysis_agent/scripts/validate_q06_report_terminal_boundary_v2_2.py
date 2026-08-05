"""Create offline evidence for the Q06 report terminal boundary V2.2."""

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
from src.native_tool_transport_mock_v2_1_revision import (  # noqa: E402
    OfflineNativeToolTransportV2_1Revision,
)
from src.online_native_tool_candidate_v2_1_revision import (  # noqa: E402
    NativeToolOnlineCandidateV2_1Revision,
)
from src.q06_report_terminal_boundary_mock import (  # noqa: E402
    Q06ReportTerminalConflictMockClient,
)
from src.q06_report_terminal_boundary_v2_2 import (  # noqa: E402
    validate_q06_report_terminal_boundary,
)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _run(*, terminal_lock: bool) -> tuple[Any, Any, Any]:
    transport = OfflineNativeToolTransportV2_1Revision(
        Q06ReportTerminalConflictMockClient(),
        q06_terminal_policy_enabled=terminal_lock,
    )
    candidate = NativeToolOnlineCandidateV2_1Revision(
        api_key="offline-placeholder-not-from-environment",
        registry=FrozenH2MockRegistry(),
        response_limit=3,
        transport=transport,
        model="deepseek-v4-flash",
        q06_terminal_lock_enabled=terminal_lock,
    )
    outcome = candidate.run_turn(
        session_id="SESSION-q06-terminal-v22",
        turn_id="TURN-006",
        question=load_frozen_questions()["Q06"]["question"],
        result_root="results/raw/q06_terminal_boundary_offline",
    )
    return outcome, candidate, transport


def _case_payload(outcome: Any, candidate: Any, transport: Any) -> dict[str, Any]:
    return {
        "status": outcome.status,
        "error_stage": outcome.error_stage,
        "error_message": outcome.error_message,
        "model_response_count": outcome.model_response_count,
        "executed_tool_sequence": [
            call.tool_name for call in outcome.tool_calls
        ],
        "fact_count": len(outcome.facts),
        "chart_count": len(outcome.charts),
        "report_validation_status": (
            None
            if outcome.report_validation is None
            else outcome.report_validation.status
        ),
        "fixed_question_validation_status": validate_fixed_question(
            "Q06", outcome
        ).status,
        "requested_tool_choices": [
            step.requested_tool_choice for step in candidate.last_trace
        ],
        "observed_actions": [step.action for step in candidate.last_trace],
        "selected_tools": [
            step.selected_tool_name for step in candidate.last_trace
        ],
        "transport_requests": len(transport.requests),
        "all_requests_visible_tool_count": [
            request.tool_count for request in transport.requests
        ],
        "real_network_opened": False,
        "real_model_called": False,
        "api_key_read_from_environment": False,
    }


def main() -> int:
    preflight = validate_q06_report_terminal_boundary()
    legacy, legacy_candidate, legacy_transport = _run(terminal_lock=False)
    redesigned, redesigned_candidate, redesigned_transport = _run(
        terminal_lock=True
    )
    legacy_payload = _case_payload(
        legacy, legacy_candidate, legacy_transport
    )
    redesigned_payload = _case_payload(
        redesigned, redesigned_candidate, redesigned_transport
    )
    passed = (
        legacy_payload["status"] == "failed"
        and legacy_payload["requested_tool_choices"]
        == ["auto", "auto", "auto"]
        and legacy_payload["selected_tools"][-1] == "get_data_profile"
        and len(legacy.tool_calls) == 2
        and redesigned_payload["status"] == "completed"
        and redesigned_payload["requested_tool_choices"]
        == ["auto", "auto", "none"]
        and redesigned_payload["selected_tools"][-1] is None
        and redesigned_payload["chart_count"] == 2
        and redesigned_payload["report_validation_status"] == "passed"
        and redesigned_payload["fixed_question_validation_status"] == "passed"
    )
    timestamp = datetime.now().astimezone().strftime(
        "%Y%m%dT%H%M%S_%f%z"
    )
    run_id = f"q06_report_terminal_boundary_offline_{timestamp}"
    output_dir = PROJECT_ROOT / "results" / "raw" / run_id
    summary = {
        "schema_version": "1.5.6-h3-q06-report-terminal-boundary-offline-v1",
        "run_id": run_id,
        "status": "passed" if passed else "failed",
        "model_configuration": preflight.model,
        "legacy_auto_case": legacy_payload,
        "redesigned_terminal_none_case": redesigned_payload,
        "single_changed_boundary": "third_response_tool_choice_auto_to_none",
        "prompt_changed": False,
        "provider_schema_changed": False,
        "data_changed": False,
        "acceptance_rules_changed": False,
        "real_network_opened": False,
        "real_model_called": False,
        "api_key_read_from_environment": False,
        "real_model_calls_allowed": False,
    }
    _write_json(output_dir / "legacy_auto_case.json", legacy_payload)
    _write_json(
        output_dir / "redesigned_terminal_none_case.json",
        redesigned_payload,
    )
    _write_json(output_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
