"""Create offline evidence for the V2.2.1 terminal JSON candidate."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent_protocol import (  # noqa: E402
    AgentProtocolError,
    parse_control_response,
)
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
from src.report_terminal_json_boundary_v2_2_1 import (  # noqa: E402
    validate_q01_q10_validation_coverage,
    validate_report_terminal_json_boundary,
)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _is_rejected(content: str) -> bool:
    try:
        parse_control_response(content)
    except AgentProtocolError:
        return True
    return False


def main() -> int:
    preflight = validate_report_terminal_json_boundary()
    coverage = validate_q01_q10_validation_coverage()
    transport = OfflineNativeToolTransportV2_1Revision(
        FrozenQuestionNativeToolMockClient(),
        q06_terminal_policy_enabled=True,
        q06_terminal_json_policy_enabled=True,
    )
    candidate = NativeToolOnlineCandidateV2_1Revision(
        api_key="offline-placeholder-not-from-environment",
        registry=FrozenH2MockRegistry(),
        response_limit=3,
        transport=transport,
        model="deepseek-v4-flash",
        q06_terminal_lock_enabled=True,
        q06_terminal_json_enabled=True,
    )
    outcome = candidate.run_turn(
        session_id="SESSION-q06-v221-json",
        turn_id="TURN-006",
        question=load_frozen_questions()["Q06"]["question"],
        result_root="results/raw/q06_v221_terminal_json_offline",
    )
    fixed = validate_fixed_question("Q06", outcome)
    tool_choices = [request.tool_choice for request in transport.requests]
    response_formats = [
        request.response_format for request in transport.requests
    ]
    tool_counts = [request.tool_count for request in transport.requests]
    trace_formats = [
        step.requested_response_format for step in candidate.last_trace
    ]
    dsml_rejected = _is_rejected(
        'Preface<||DSML||tool_calls><||DSML||invoke '
        'name="final_report">{"response_type":"report"}'
    )
    wrong_schema_rejected = _is_rejected('{"response_type":"report"}')
    passed = (
        outcome.status == "completed"
        and fixed.status == "passed"
        and tool_choices == ["auto", "auto", "none"]
        and response_formats
        == [None, None, {"type": "json_object"}]
        and trace_formats == response_formats
        and tool_counts == [7, 7, 7]
        and len(outcome.tool_calls) == 2
        and len(outcome.charts) == 2
        and outcome.report_validation is not None
        and outcome.report_validation.status == "passed"
        and dsml_rejected
        and wrong_schema_rejected
    )
    timestamp = datetime.now().astimezone().strftime(
        "%Y%m%dT%H%M%S_%f%z"
    )
    run_id = f"report_terminal_json_v2_2_1_offline_{timestamp}"
    output_dir = PROJECT_ROOT / "results" / "raw" / run_id
    summary = {
        "schema_version": (
            "1.5.6-h3-report-terminal-json-v2.2.1-offline-v1"
        ),
        "run_id": run_id,
        "status": "passed" if passed else "failed",
        "question_id": "Q06",
        "model_configuration": preflight.model,
        "tool_choice_sequence": tool_choices,
        "response_format_sequence": response_formats,
        "tool_visibility_each_response": tool_counts,
        "trace_response_format_sequence": trace_formats,
        "executed_tool_sequence": [
            call.tool_name for call in outcome.tool_calls
        ],
        "outcome_status": outcome.status,
        "fixed_question_validation_status": fixed.status,
        "report_validation_status": (
            None
            if outcome.report_validation is None
            else outcome.report_validation.status
        ),
        "chart_count": len(outcome.charts),
        "dsml_pseudo_tool_markup_rejected": dsml_rejected,
        "valid_json_wrong_schema_rejected": wrong_schema_rejected,
        "coverage_questions_audited": len(coverage["questions"]),
        "current_native_flash_real_passed_questions": [],
        "current_native_flash_real_failed_questions": ["Q06"],
        "current_native_flash_real_not_run_questions": [
            item["question_id"]
            for item in coverage["questions"]
            if item["current_native_flash_real"] == "not_run"
        ],
        "real_network_opened": False,
        "real_model_called": False,
        "api_key_read_from_environment": False,
        "automatic_retry_count": 0,
        "real_model_calls_allowed": False,
        "privacy_audit": {
            "api_key_saved": False,
            "authorization_header_value_saved": False,
            "request_body_saved": False,
            "raw_customer_id_exported": False,
            "local_absolute_paths_saved": False,
        },
    }
    _write_json(output_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
