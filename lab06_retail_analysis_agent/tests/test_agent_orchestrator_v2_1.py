from __future__ import annotations

import json
import unittest

from src.agent_orchestrator_v2_1 import (
    RetailAgentOrchestratorV2_1,
)
from src.deepseek_client import (
    ChatCompletionResult,
    ProviderToolCall,
)
from src.fixed_question_validation import (
    load_frozen_questions,
    validate_fixed_question,
)
from src.mock_h2_registry import FrozenH2MockRegistry
from src.mock_v2_1_client import FrozenQuestionV2_1MockClient


EXPECTED_TOOLS = {
    "Q01": ["get_sales_overview"],
    "Q02": ["rank_products"],
    "Q03": ["analyze_regions"],
    "Q04": ["analyze_time_trend"],
    "Q05": ["get_sales_overview", "compare_segments"],
    "Q06": ["analyze_time_trend", "rank_products"],
    "Q07": ["get_sales_overview", "analyze_customers"],
    "Q08": [],
    "Q09": [],
    "Q10": [],
}
EXPECTED_RESPONSES = {
    "Q01": 3,
    "Q02": 3,
    "Q03": 3,
    "Q04": 3,
    "Q05": 4,
    "Q06": 4,
    "Q07": 4,
    "Q08": 1,
    "Q09": 1,
    "Q10": 1,
}


class ChangedArgumentMockClient(FrozenQuestionV2_1MockClient):
    def complete_strict_tools(self, *, messages, tools):
        response = super().complete_strict_tools(
            messages=messages,
            tools=tools,
        )
        call = response.tool_calls[0]
        changed = dict(call.arguments)
        changed["top_n"] = 4
        return ChatCompletionResult(
            finish_reason=response.finish_reason,
            content=response.content,
            tool_calls=(
                ProviderToolCall(
                    provider_call_id=call.provider_call_id,
                    tool_name=call.tool_name,
                    arguments=changed,
                ),
            ),
            raw_response=response.raw_response,
            usage=None,
        )


class FreeNarrativeMockClient(FrozenQuestionV2_1MockClient):
    def complete_json(self, *, messages):
        response = super().complete_json(messages=messages)
        if response.raw_response["phase"] != "semantic_report":
            return response
        payload = json.loads(response.content)
        payload["sections"][1]["blocks"][0]["narrative"] = (
            "模型自行补充的事实叙述。"
        )
        return ChatCompletionResult(
            finish_reason="stop",
            content=json.dumps(payload, ensure_ascii=False),
            tool_calls=(),
            raw_response={
                "mock": True,
                "phase": "semantic_report",
                "payload": payload,
            },
            usage=None,
        )


class AgentOrchestratorV2_1Tests(unittest.TestCase):
    def test_all_frozen_questions_pass_end_to_end(self) -> None:
        questions = load_frozen_questions()
        client = FrozenQuestionV2_1MockClient()
        orchestrator = RetailAgentOrchestratorV2_1(
            client=client,
            registry=FrozenH2MockRegistry(),
        )

        outcomes = {}
        validations = {}
        for index, question_id in enumerate(
            questions,
            start=1,
        ):
            outcome = orchestrator.run_turn(
                session_id="SESSION-v21-e2e",
                turn_id=f"TURN-{index:03d}",
                question=questions[question_id]["question"],
                result_root="results/raw/v2_1_e2e_test",
            )
            validation = validate_fixed_question(
                question_id,
                outcome,
            )
            outcomes[question_id] = outcome
            validations[question_id] = validation

        self.assertEqual(
            {
                question_id: validation.status
                for question_id, validation in validations.items()
            },
            {question_id: "passed" for question_id in questions},
        )
        for question_id, outcome in outcomes.items():
            self.assertEqual(
                [call.tool_name for call in outcome.tool_calls],
                EXPECTED_TOOLS[question_id],
            )
            self.assertEqual(
                outcome.model_response_count,
                EXPECTED_RESPONSES[question_id],
            )

        for question_id in (
            "Q01",
            "Q02",
            "Q03",
            "Q04",
            "Q05",
            "Q06",
            "Q07",
        ):
            outcome = outcomes[question_id]
            self.assertEqual(outcome.status, "completed")
            self.assertEqual(
                outcome.report_validation.status,
                "passed",
            )
            self.assertNotIn(
                "显著份额",
                outcome.report_markdown,
            )
            self.assertNotIn(
                "驱动峰值",
                outcome.report_markdown,
            )
            self.assertNotIn(
                "narrative",
                outcome.report_plan.model_dump_json(),
            )

        self.assertEqual(
            outcomes["Q08"].status,
            "needs_clarification",
        )
        self.assertEqual(outcomes["Q09"].status, "boundary")
        self.assertEqual(outcomes["Q10"].status, "boundary")
        self.assertEqual(client.json_calls, 17)
        self.assertEqual(client.strict_tool_calls, 10)

    def test_q06_dependency_is_bound_to_peak_fact(self) -> None:
        question = load_frozen_questions()["Q06"]["question"]
        outcome = RetailAgentOrchestratorV2_1(
            client=FrozenQuestionV2_1MockClient(),
            registry=FrozenH2MockRegistry(),
        ).run_turn(
            session_id="SESSION-v21-q06",
            turn_id="TURN-001",
            question=question,
        )

        self.assertEqual(outcome.status, "completed")
        self.assertEqual(
            outcome.tool_calls[1].dependency_fact_ids,
            ("FACT-001",),
        )
        self.assertEqual(
            outcome.tool_calls[1].arguments["start_date"],
            "2011-11-01",
        )
        self.assertEqual(
            outcome.tool_calls[1].arguments["end_date"],
            "2011-11-30",
        )
        self.assertIn("£1,503,866.78", outcome.report_markdown)
        self.assertNotIn("£10,004,320.47", outcome.report_markdown)

    def test_model_cannot_change_program_expanded_arguments(
        self,
    ) -> None:
        question = load_frozen_questions()["Q02"]["question"]
        outcome = RetailAgentOrchestratorV2_1(
            client=ChangedArgumentMockClient(),
            registry=FrozenH2MockRegistry(),
        ).run_turn(
            session_id="SESSION-v21-bad-args",
            turn_id="TURN-001",
            question=question,
        )

        self.assertEqual(outcome.status, "failed")
        self.assertEqual(outcome.error_stage, "recipe_execution")
        self.assertIn(
            "参数与程序展开参数不一致",
            outcome.error_message,
        )
        self.assertEqual(len(outcome.tool_calls), 0)

    def test_free_report_narrative_is_rejected_in_orchestration(
        self,
    ) -> None:
        question = load_frozen_questions()["Q01"]["question"]
        outcome = RetailAgentOrchestratorV2_1(
            client=FreeNarrativeMockClient(),
            registry=FrozenH2MockRegistry(),
        ).run_turn(
            session_id="SESSION-v21-bad-report",
            turn_id="TURN-001",
            question=question,
        )

        self.assertEqual(outcome.status, "failed")
        self.assertEqual(outcome.error_stage, "semantic_report")
        self.assertIsNone(outcome.report_markdown)


if __name__ == "__main__":
    unittest.main()
