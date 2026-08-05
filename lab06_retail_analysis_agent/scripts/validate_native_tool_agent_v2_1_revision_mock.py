"""Run Q01-Q10 through the independent, network-free native-tool mock."""

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
from src.native_tool_agent_v2_1_revision import (  # noqa: E402
    RetailNativeToolAgentV2_1Revision,
)
from src.prompt_contract import (  # noqa: E402
    load_native_tool_agent_prompts_evidence_guard_v1,
)


ACCEPTED_OFFLINE_HARNESS_STATUSES = {
    "protocol_and_dataflow_passed",
    "passed_deterministic_pending_manual_review",
}


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _outcome_payload(outcome: Any) -> dict[str, Any]:
    return {
        "status": outcome.status,
        "session_id": outcome.session_id,
        "turn_id": outcome.turn_id,
        "original_question": outcome.original_question,
        "model_response_count": outcome.model_response_count,
        "tool_calls": [
            {
                "call_id": call.call_id,
                "provider_call_id": call.provider_call_id,
                "tool_name": call.tool_name,
                "arguments": call.arguments,
                "result_path": call.result_path,
                "result": call.result,
                "facts": [
                    fact.model_dump(mode="json") for fact in call.facts
                ],
            }
            for call in outcome.tool_calls
        ],
        "facts": [fact.model_dump(mode="json") for fact in outcome.facts],
        "charts": [chart.model_dump(mode="json") for chart in outcome.charts],
        "report_draft": (
            None
            if outcome.report_draft is None
            else outcome.report_draft.model_dump(mode="json")
        ),
        "report_markdown": outcome.report_markdown,
        "report_validation": (
            None
            if outcome.report_validation is None
            else outcome.report_validation.model_dump(mode="json")
        ),
        "clarification": (
            None
            if outcome.clarification is None
            else outcome.clarification.model_dump(mode="json")
        ),
        "boundary": (
            None
            if outcome.boundary is None
            else outcome.boundary.model_dump(mode="json")
        ),
        "error_stage": outcome.error_stage,
        "error_message": outcome.error_message,
        "raw_responses": list(outcome.raw_responses),
    }


def main() -> int:
    timestamp = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S_%f%z")
    output_dir = (
        PROJECT_ROOT
        / "results"
        / "raw"
        / f"native_tool_mock_v2_1_revision_{timestamp}"
    )
    relative_result_root = (
        f"results/raw/native_tool_mock_v2_1_revision_{timestamp}"
    )
    questions = load_frozen_questions()
    prompts = load_native_tool_agent_prompts_evidence_guard_v1()

    passed = 0
    total_model_responses = 0
    total_tool_calls = 0
    total_facts = 0
    total_charts = 0
    visibility_checks = 0
    all_outputs: list[str] = []

    for index in range(1, 11):
        question_id = f"Q{index:02d}"
        client = FrozenQuestionNativeToolMockClient()
        agent = RetailNativeToolAgentV2_1Revision(
            client=client,
            registry=FrozenH2MockRegistry(),
            prompts=prompts,
        )
        outcome = agent.run_turn(
            session_id="SESSION-native-mock-audit",
            turn_id=f"TURN-{index:03d}",
            question=questions[question_id]["question"],
            result_root=relative_result_root,
        )
        validation = validate_fixed_question(question_id, outcome)
        trace = [
            {
                "response_index": step.response_index,
                "visible_tool_names": list(step.visible_tool_names),
                "visible_tool_count": len(step.visible_tool_names),
                "action": step.action,
                "selected_tool_name": step.selected_tool_name,
                "selected_arguments": step.selected_arguments,
                "normalized_arguments": step.normalized_arguments,
                "tool_result_messages_seen": (
                    step.tool_result_messages_seen
                ),
                "requested_tool_choice": step.requested_tool_choice,
            }
            for step in agent.last_trace
        ]
        record = {
            "question_id": question_id,
            "question_type": questions[question_id]["type"],
            "transport": "offline_mock_no_network",
            "model_called": False,
            "native_model_trace": trace,
            "outcome": _outcome_payload(outcome),
            "fixed_answer_validation": validation.model_dump(mode="json"),
        }
        _write_json(output_dir / f"{question_id}.json", record)
        all_outputs.append(json.dumps(record, ensure_ascii=False))

        passed += validation.status in ACCEPTED_OFFLINE_HARNESS_STATUSES
        total_model_responses += outcome.model_response_count
        total_tool_calls += len(outcome.tool_calls)
        total_facts += len(outcome.facts)
        total_charts += len(outcome.charts)
        visibility_checks += sum(
            item["visible_tool_count"] == 7 for item in trace
        )

    joined = "\n".join(all_outputs)
    privacy_audit = {
        "api_key_present": "LLM_API_KEY" in joined or "Bearer " in joined,
        "authorization_header_present": "Authorization" in joined,
        "raw_customer_id_export_detected": (
            '"customer_id"' in joined.lower()
            or '"customerid"' in joined.lower()
        ),
    }
    summary = {
        "schema_version": "1.5.6-h3-native-tool-mock-audit-v1",
        "stage": "independent_native_tool_mock_orchestrator",
        "status": (
            "passed"
            if passed == 10
            and visibility_checks == total_model_responses
            and not any(privacy_audit.values())
            else "failed"
        ),
        "real_model_called": False,
        "network_used": False,
        "api_key_read": False,
        "recipe_router_used": False,
        "questions_passed": passed,
        "questions_total": 10,
        "model_response_count": total_model_responses,
        "tool_call_count": total_tool_calls,
        "fact_count": total_facts,
        "chart_count": total_charts,
        "seven_tool_visibility_checks_passed": visibility_checks,
        "prompt_versions": {
            "system": prompts.system.version,
            "report": prompts.report.version,
        },
        "prompt_hashes": {
            "system": prompts.system.sha256,
            "report": prompts.report.sha256,
        },
        "privacy_audit": privacy_audit,
        "q06_dependency_expectation": {
            "first_tool": "analyze_time_trend",
            "second_tool": "rank_products",
            "second_call_reads_one_tool_result": True,
            "derived_start_date": "2011-11-01",
            "derived_end_date": "2011-11-30",
        },
    }
    _write_json(output_dir / "summary.json", summary)
    print(json.dumps({**summary, "output_dir": str(output_dir)}, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
