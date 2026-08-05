"""Offline preflight for the single-Q06 real revalidation checkpoint."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.deepseek_provider_schema_adapter_v2_1_revision import (  # noqa: E402
    DEEPSEEK_NONE_SENTINEL,
    adapt_deepseek_provider_schema,
)
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
from src.q06_provider_schema_revalidation_mock import (  # noqa: E402
    Q06ProviderSchemaRevalidationMockClient,
)
from src.q06_real_revalidation_plan_v2_1_revision import (  # noqa: E402
    PLAN_PATH,
    validate_q06_real_revalidation_plan,
)


def _walk(value: Any):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _provider_schema_audit() -> dict[str, Any]:
    schemas = [
        adapt_deepseek_provider_schema(item)
        for item in FrozenH2MockRegistry().provider_schemas()
    ]
    nodes = [node for schema in schemas for node in _walk(schema)]
    null_type_count = sum(
        isinstance(node, dict) and node.get("type") == "null"
        for node in nodes
    )
    nonnumeric_const_count = sum(
        isinstance(node, dict)
        and "const" in node
        and (
            isinstance(node["const"], (str, bool))
            or not isinstance(node["const"], (int, float))
        )
        for node in nodes
    )
    sentinel_count = sum(
        isinstance(node, dict)
        and node.get("enum") == [DEEPSEEK_NONE_SENTINEL]
        for node in nodes
    )
    return {
        "tool_count": len(schemas),
        "null_type_count": null_type_count,
        "nonnumeric_const_count": nonnumeric_const_count,
        "none_sentinel_enum_count": sentinel_count,
        "passed": (
            len(schemas) == 7
            and null_type_count == 0
            and nonnumeric_const_count == 0
            and sentinel_count == 13
        ),
    }


def main() -> int:
    preflight = validate_q06_real_revalidation_plan()
    timestamp = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S_%f%z")
    run_id = f"q06_real_revalidation_plan_preflight_{timestamp}"
    output_dir = PROJECT_ROOT / "results" / "raw" / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    transport = OfflineNativeToolTransportV2_1Revision(
        Q06ProviderSchemaRevalidationMockClient()
    )
    candidate = NativeToolOnlineCandidateV2_1Revision(
        api_key="offline-q06-revalidation-placeholder",
        registry=FrozenH2MockRegistry(),
        response_limit=3,
        transport=transport,
        question_count=1,
    )
    outcome = candidate.run_turn(
        session_id="SESSION-q06-real-revalidation-preflight",
        turn_id="TURN-006",
        question=load_frozen_questions()["Q06"]["question"],
        result_root=f"results/raw/{run_id}",
    )
    validation = validate_fixed_question("Q06", outcome)
    trace = candidate.last_trace
    snapshot = candidate.response_limit_snapshot()
    schema_audit = _provider_schema_audit()

    trace_passed = (
        len(trace) == 3
        and trace[0].selected_tool_name == "analyze_time_trend"
        and trace[0].selected_arguments is not None
        and trace[0].selected_arguments.get("start_date")
        == DEEPSEEK_NONE_SENTINEL
        and trace[0].selected_arguments.get("end_date")
        == DEEPSEEK_NONE_SENTINEL
        and trace[0].selected_arguments.get("grain") == "month"
        and trace[0].normalized_arguments is not None
        and trace[0].normalized_arguments.get("start_date") is None
        and trace[0].normalized_arguments.get("end_date") is None
        and trace[1].selected_tool_name == "rank_products"
        and trace[1].selected_arguments is not None
        and trace[1].selected_arguments.get("start_date") == "2011-11-01"
        and trace[1].selected_arguments.get("end_date") == "2011-11-30"
        and trace[1].tool_result_messages_seen == 1
        and trace[2].action == "control_response"
        and trace[2].tool_result_messages_seen == 2
    )
    request_contract_passed = (
        len(transport.requests) == 3
        and all(
            request.tool_count == 7
            and request.all_tools_strict
            and request.all_parameters_closed
            and request.tool_choice == "auto"
            and request.thinking_disabled
            and not request.response_format_present
            for request in transport.requests
        )
    )
    passed = (
        preflight.status == "passed"
        and validation.status == "passed"
        and outcome.status == "completed"
        and trace_passed
        and request_contract_passed
        and schema_audit["passed"]
        and snapshot.attempted == 3
        and snapshot.completed == 3
        and snapshot.failed == 0
    )
    summary = {
        "schema_version": "1.5.6-h3-q06-real-revalidation-offline-preflight-v1",
        "run_id": run_id,
        "status": "passed" if passed else "failed",
        "plan_path": str(PLAN_PATH.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "question_ids": ["Q06"],
        "model": preflight.model,
        "response_attempt_upper_bound": 3,
        "automatic_retry_count": 0,
        "real_network_opened": False,
        "api_key_read": False,
        "real_model_called": False,
        "real_model_calls_allowed": False,
        "guarded_real_runner_implemented": False,
        "request_contract_passed": request_contract_passed,
        "provider_schema_audit": schema_audit,
        "fixed_question_validation_status": validation.status,
        "outcome_status": outcome.status,
        "tool_sequence": [call.tool_name for call in outcome.tool_calls],
        "fact_count": len(outcome.facts),
        "chart_count": len(outcome.charts),
        "report_validation_status": outcome.report_validation.status,
        "trace_passed": trace_passed,
        "native_trace": [
            {
                "response_index": step.response_index,
                "action": step.action,
                "selected_tool_name": step.selected_tool_name,
                "selected_arguments": step.selected_arguments,
                "normalized_arguments": step.normalized_arguments,
                "tool_result_messages_seen": step.tool_result_messages_seen,
                "requested_tool_choice": step.requested_tool_choice,
                "visible_tool_count": len(step.visible_tool_names),
            }
            for step in trace
        ],
        "response_limit_snapshot": {
            "limit": snapshot.limit,
            "attempted": snapshot.attempted,
            "completed": snapshot.completed,
            "failed": snapshot.failed,
        },
        "checks": list(preflight.checks),
        "next_gate": "用户审阅并冻结候选计划；冻结本身不授权真实调用",
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {**summary, "output_dir": str(output_dir)},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
