"""Run Q01-Q10 through the independent V2.1 Mock orchestrator."""

from __future__ import annotations

import json
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
from src.fixed_question_validation import (  # noqa: E402
    load_frozen_questions,
    validate_fixed_question,
)
from src.mock_h2_registry import FrozenH2MockRegistry  # noqa: E402
from src.mock_v2_1_client import (  # noqa: E402
    FrozenQuestionV2_1MockClient,
)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


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
    client = FrozenQuestionV2_1MockClient()
    orchestrator = RetailAgentOrchestratorV2_1(
        client=client,
        registry=FrozenH2MockRegistry(),
    )
    run_id = datetime.now().astimezone().strftime(
        "v2_1_mock_e2e_%Y%m%dT%H%M%S_%f%z"
    )
    relative_root = f"results/raw/{run_id}"
    output_root = PROJECT_ROOT / relative_root
    session_id = f"SESSION-{run_id.replace('+', '_')}"
    results = []
    total_facts = 0
    total_tools = 0
    total_responses = 0

    for index, (question_id, question) in enumerate(
        questions.items(),
        start=1,
    ):
        turn_id = f"TURN-{index:03d}"
        outcome = orchestrator.run_turn(
            session_id=session_id,
            turn_id=turn_id,
            question=question["question"],
            result_root=relative_root,
        )
        validation = validate_fixed_question(
            question_id,
            outcome,
        )
        turn_root = output_root / turn_id
        _write_json(
            turn_root / "outcome.json",
            _serialize_outcome(outcome),
        )
        _write_json(
            turn_root / "raw_mock_responses.json",
            list(outcome.raw_responses),
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

        total_facts += len(outcome.facts)
        total_tools += len(outcome.tool_calls)
        total_responses += outcome.model_response_count
        results.append(
            {
                "question_id": question_id,
                "type": question["type"],
                "outcome_status": outcome.status,
                "fixed_question_status": validation.status,
                "model_response_count": (
                    outcome.model_response_count
                ),
                "tool_sequence": [
                    call.tool_name for call in outcome.tool_calls
                ],
                "dependency_fact_ids": [
                    {
                        "call_id": call.call_id,
                        "fact_ids": list(
                            call.dependency_fact_ids
                        ),
                    }
                    for call in outcome.tool_calls
                    if call.dependency_fact_ids
                ],
                "fact_count": len(outcome.facts),
                "report_validation_status": (
                    None
                    if outcome.report_validation is None
                    else outcome.report_validation.status
                ),
                "issue_count": len(validation.issues),
                "manual_review_items": (
                    validation.manual_review_items
                ),
            }
        )

    summary = {
        "schema_version": "1.5.6-h3-v2.1-mock-e2e-v1",
        "run_id": run_id,
        "execution_mode": "mock_agent_offline",
        "real_model_called": False,
        "question_count": len(results),
        "passed": sum(
            item["fixed_question_status"] == "passed"
            for item in results
        ),
        "failed": sum(
            item["fixed_question_status"] == "failed"
            for item in results
        ),
        "model_response_count": total_responses,
        "json_response_count": client.json_calls,
        "strict_tool_response_count": client.strict_tool_calls,
        "tool_call_count": total_tools,
        "fact_count": total_facts,
        "results": results,
        "privacy_assertions": {
            "api_key_saved": False,
            "authorization_header_saved": False,
            "raw_retail_rows_used": False,
            "customer_id_values_exported": False,
            "absolute_paths_saved": False,
        },
    }
    _write_json(output_root / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
