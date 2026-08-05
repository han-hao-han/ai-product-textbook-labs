"""Run Q01-Q10 through the real DeepSeek client with an injected transport."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.agent_orchestrator_v2_1 import (  # noqa: E402
    AgentTurnOutcomeV2_1,
    RetailAgentOrchestratorV2_1,
)
from src.deepseek_client import (  # noqa: E402
    DEEPSEEK_MODEL,
    DeepSeekChatClient,
)
from src.deepseek_transport_mock_v2_1 import (  # noqa: E402
    OfflineDeepSeekTransportV2_1,
)
from src.fixed_question_validation import (  # noqa: E402
    load_frozen_questions,
    validate_fixed_question,
)
from src.mock_h2_registry import FrozenH2MockRegistry  # noqa: E402
from src.mock_v2_1_client import (  # noqa: E402
    FrozenQuestionV2_1MockClient,
)
from src.online_candidate_v2_1 import (  # noqa: E402
    ResponseLimitedClientV2_1,
)


QUESTION_IDS = tuple(f"Q{index:02d}" for index in range(1, 11))
EXPECTED_RESPONSE_LIMIT = 27
OFFLINE_PLACEHOLDER_KEY = "offline-placeholder-not-a-secret"


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _session_id(run_id: str) -> str:
    return "SESSION-" + re.sub(r"[^A-Za-z0-9_-]", "_", run_id)


def _serialize_outcome(
    outcome: AgentTurnOutcomeV2_1,
) -> dict[str, Any]:
    return {
        "status": outcome.status,
        "session_id": outcome.session_id,
        "turn_id": outcome.turn_id,
        "original_question": outcome.original_question,
        "model_response_count": outcome.model_response_count,
        "decision": (
            None
            if outcome.decision is None
            else outcome.decision.model_dump(mode="json")
        ),
        "tool_calls": [
            {
                "call_id": call.call_id,
                "provider_call_id": call.provider_call_id,
                "tool_name": call.tool_name,
                "arguments": call.arguments,
                "result_path": call.result_path,
                "dependency_fact_ids": list(
                    call.dependency_fact_ids
                ),
            }
            for call in outcome.tool_calls
        ],
        "facts": [
            fact.model_dump(mode="json") for fact in outcome.facts
        ],
        "report_plan": (
            None
            if outcome.report_plan is None
            else outcome.report_plan.model_dump(mode="json")
        ),
        "report_validation": (
            None
            if outcome.report_validation is None
            else outcome.report_validation.model_dump(mode="json")
        ),
        "report_markdown": outcome.report_markdown,
        "error_stage": outcome.error_stage,
        "error_message": outcome.error_message,
    }


def main() -> int:
    questions = load_frozen_questions()
    logical_mock = FrozenQuestionV2_1MockClient()
    transport = OfflineDeepSeekTransportV2_1(logical_mock)
    provider_client = DeepSeekChatClient(
        api_key=OFFLINE_PLACEHOLDER_KEY,
        transport=transport,
    )
    limited_client = ResponseLimitedClientV2_1(
        provider_client,
        limit=EXPECTED_RESPONSE_LIMIT,
    )
    orchestrator = RetailAgentOrchestratorV2_1(
        client=limited_client,
        registry=FrozenH2MockRegistry(),
    )
    run_id = datetime.now().astimezone().strftime(
        "v2_1_transport_%Y%m%dT%H%M%S_%f%z"
    )
    relative_root = f"results/raw/{run_id}"
    output_root = PROJECT_ROOT / relative_root
    session_id = _session_id(run_id)
    results: list[dict[str, Any]] = []

    for index, question_id in enumerate(QUESTION_IDS, start=1):
        turn_id = f"TURN-{index:03d}"
        outcome = orchestrator.run_turn(
            session_id=session_id,
            turn_id=turn_id,
            question=questions[question_id]["question"],
            result_root=relative_root,
        )
        validation = validate_fixed_question(question_id, outcome)
        turn_root = output_root / turn_id
        _write_json(
            turn_root / "provider_raw_responses.json",
            list(outcome.raw_responses),
        )
        _write_json(
            turn_root / "outcome.json",
            _serialize_outcome(outcome),
        )
        _write_json(
            turn_root / "fixed_question_validation.json",
            validation.model_dump(mode="json"),
        )
        if outcome.report_markdown is not None:
            (turn_root / "report.md").write_text(
                outcome.report_markdown,
                encoding="utf-8",
            )
        for call in outcome.tool_calls:
            _write_json(PROJECT_ROOT / call.result_path, call.result)
        results.append(
            {
                "question_id": question_id,
                "outcome_status": outcome.status,
                "fixed_question_status": validation.status,
                "model_response_count": outcome.model_response_count,
                "tool_sequence": [
                    call.tool_name for call in outcome.tool_calls
                ],
                "fact_count": len(outcome.facts),
                "report_validation_status": (
                    None
                    if outcome.report_validation is None
                    else outcome.report_validation.status
                ),
                "error_stage": outcome.error_stage,
                "error_message": outcome.error_message,
            }
        )

    audit = transport.audit_payload()
    audit_text = json.dumps(audit, ensure_ascii=False)
    snapshot = limited_client.snapshot()
    standard_count = sum(
        request["endpoint_kind"] == "standard_json"
        for request in audit["requests"]
    )
    strict_count = sum(
        request["endpoint_kind"] == "beta_strict_tool"
        for request in audit["requests"]
    )
    all_request_contracts_passed = all(
        request["model"] == DEEPSEEK_MODEL
        and request["thinking_disabled"] is True
        and request["temperature"] == 0
        and request["stream"] is False
        and request["authorization_header_present"] is True
        and request["authorization_scheme"] == "Bearer"
        for request in audit["requests"]
    )
    summary = {
        "schema_version": "1.5.6-h3-v2.1-offline-transport-v1",
        "run_id": run_id,
        "execution_mode": "offline_injected_transport",
        "real_network_opened": False,
        "real_model_called": False,
        "question_count": len(QUESTION_IDS),
        "passed": sum(
            result["fixed_question_status"] == "passed"
            for result in results
        ),
        "failed": sum(
            result["fixed_question_status"] == "failed"
            for result in results
        ),
        "response_limit": snapshot.limit,
        "requests_attempted": snapshot.attempted,
        "responses_completed": snapshot.completed,
        "transport_failures": snapshot.failed,
        "standard_json_requests": standard_count,
        "beta_strict_tool_requests": strict_count,
        "all_request_contracts_passed": (
            all_request_contracts_passed
        ),
        "results": results,
        "privacy_assertions": {
            "placeholder_key_saved": (
                OFFLINE_PLACEHOLDER_KEY in audit_text
            ),
            "authorization_value_saved": False,
            "request_body_saved": False,
            "raw_retail_rows_sent": False,
            "customer_id_values_sent": False,
            "absolute_paths_saved": False,
        },
    }
    _write_json(output_root / "transport_audit.json", audit)
    _write_json(output_root / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if (
        summary["passed"] == len(QUESTION_IDS)
        and summary["failed"] == 0
        and snapshot.attempted == EXPECTED_RESPONSE_LIMIT
        and snapshot.completed == EXPECTED_RESPONSE_LIMIT
        and snapshot.failed == 0
        and standard_count == 17
        and strict_count == 10
        and all_request_contracts_passed
        and not summary["privacy_assertions"][
            "placeholder_key_saved"
        ]
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
