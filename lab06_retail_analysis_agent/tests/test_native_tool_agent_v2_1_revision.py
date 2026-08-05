from __future__ import annotations

import unittest
from typing import Any

from src.deepseek_client import ChatCompletionResult, ProviderToolCall
from src.fixed_question_validation import (
    load_frozen_questions,
    validate_fixed_question,
)
from src.mock_h2_registry import FrozenH2MockRegistry
from src.mock_native_tool_client_v2_1_revision import (
    FrozenQuestionNativeToolMockClient,
)
from src.native_tool_agent_v2_1_revision import (
    FROZEN_TOOL_NAMES,
    RetailNativeToolAgentV2_1Revision,
)
from src.prompt_contract import (
    load_native_tool_agent_prompts_v2_1_revision,
)


class InvalidQ01ArgumentsClient:
    def complete_strict_tools(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: str = "auto",
    ) -> ChatCompletionResult:
        return ChatCompletionResult(
            finish_reason="tool_calls",
            content=None,
            tool_calls=(
                ProviderToolCall(
                    provider_call_id="invalid-1",
                    tool_name="get_sales_overview",
                    arguments={
                        "period": "all_data",
                        "start_date": None,
                        "end_date": None,
                        "include_incomplete_period_warning": True,
                        "model_calculated_value": "forbidden",
                    },
                ),
            ),
            raw_response={"offline_mock": True},
            usage=None,
        )


class WrongQ06DependencyClient:
    def __init__(self) -> None:
        self.delegate = FrozenQuestionNativeToolMockClient()

    def complete_strict_tools(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: str = "auto",
    ) -> ChatCompletionResult:
        result = self.delegate.complete_strict_tools(
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
        )
        if (
            result.tool_calls
            and result.tool_calls[0].tool_name == "rank_products"
        ):
            selected = result.tool_calls[0]
            wrong = dict(selected.arguments)
            wrong["start_date"] = "2011-10-01"
            return ChatCompletionResult(
                finish_reason=result.finish_reason,
                content=result.content,
                tool_calls=(
                    ProviderToolCall(
                        provider_call_id=selected.provider_call_id,
                        tool_name=selected.tool_name,
                        arguments=wrong,
                    ),
                ),
                raw_response=result.raw_response,
                usage=result.usage,
            )
        return result


class NativeToolAgentV2_1RevisionTests(unittest.TestCase):
    def test_q01_to_q10_pass_independent_native_mock_e2e(self) -> None:
        questions = load_frozen_questions()
        outcomes = {}
        traces = {}
        total_responses = 0
        for index in range(1, 11):
            question_id = f"Q{index:02d}"
            agent = RetailNativeToolAgentV2_1Revision(
                client=FrozenQuestionNativeToolMockClient(),
                registry=FrozenH2MockRegistry(),
            )
            outcome = agent.run_turn(
                session_id="SESSION-native-mock",
                turn_id=f"TURN-{index:03d}",
                question=questions[question_id]["question"],
            )
            outcomes[question_id] = outcome
            traces[question_id] = agent.last_trace
            total_responses += outcome.model_response_count

        validations = {
            question_id: validate_fixed_question(question_id, outcome)
            for question_id, outcome in outcomes.items()
        }
        self.assertEqual(
            [validations[f"Q{index:02d}"].status for index in range(1, 8)],
            ["protocol_and_dataflow_passed"] * 7,
        )
        self.assertEqual(
            [validations[f"Q{index:02d}"].status for index in range(8, 11)],
            ["passed_deterministic_pending_manual_review"] * 3,
        )
        self.assertTrue(
            all(
                item.real_model_validation_status
                == "current_model_real_status_unknown"
                for item in validations.values()
            )
        )
        self.assertEqual(total_responses, 20)
        self.assertEqual(
            sum(len(outcome.tool_calls) for outcome in outcomes.values()),
            10,
        )
        self.assertEqual(
            sum(len(outcome.charts) for outcome in outcomes.values()),
            6,
        )
        for question_trace in traces.values():
            for step in question_trace:
                self.assertEqual(len(step.visible_tool_names), 7)
                self.assertEqual(
                    set(step.visible_tool_names), set(FROZEN_TOOL_NAMES)
                )

    def test_q06_second_model_choice_uses_first_call_fact(self) -> None:
        question = load_frozen_questions()["Q06"]["question"]
        agent = RetailNativeToolAgentV2_1Revision(
            client=FrozenQuestionNativeToolMockClient(),
            registry=FrozenH2MockRegistry(),
        )
        outcome = agent.run_turn(
            session_id="SESSION-native-q06",
            turn_id="TURN-006",
            question=question,
        )

        self.assertEqual(outcome.status, "completed")
        self.assertEqual(
            [step.action for step in agent.last_trace],
            ["tool_call", "tool_call", "control_response"],
        )
        self.assertEqual(
            [step.selected_tool_name for step in agent.last_trace],
            ["analyze_time_trend", "rank_products", None],
        )
        self.assertEqual(
            agent.last_trace[1].tool_result_messages_seen, 1
        )
        self.assertEqual(
            [step.requested_tool_choice for step in agent.last_trace],
            ["auto", "auto", "none"],
        )
        self.assertEqual(
            agent.last_trace[1].selected_arguments,
            {
                "period": "custom",
                "start_date": "2011-11-01",
                "end_date": "2011-11-30",
                "metric": "sales_amount",
                "top_n": 3,
            },
        )
        self.assertEqual(
            {chart.call_id for chart in outcome.charts},
            {"CALL-001", "CALL-002"},
        )
        referenced = set(outcome.report_validation.referenced_fact_ids)
        self.assertTrue(
            any(fact.call_id == "CALL-001" and fact.fact_id in referenced
                for fact in outcome.facts)
        )
        self.assertTrue(
            any(fact.call_id == "CALL-002" and fact.fact_id in referenced
                for fact in outcome.facts)
        )

    def test_schema_rejects_model_arguments_without_program_repair(self) -> None:
        outcome = RetailNativeToolAgentV2_1Revision(
            client=InvalidQ01ArgumentsClient(),
            registry=FrozenH2MockRegistry(),
        ).run_turn(
            session_id="SESSION-native-invalid",
            turn_id="TURN-001",
            question=load_frozen_questions()["Q01"]["question"],
        )

        self.assertEqual(outcome.status, "failed")
        self.assertEqual(outcome.error_stage, "argument_schema")
        self.assertEqual(outcome.tool_calls, ())

    def test_q06_wrong_fact_dependent_arguments_stop_before_second_tool(self) -> None:
        outcome = RetailNativeToolAgentV2_1Revision(
            client=WrongQ06DependencyClient(),
            registry=FrozenH2MockRegistry(),
        ).run_turn(
            session_id="SESSION-native-q06-wrong",
            turn_id="TURN-006",
            question=load_frozen_questions()["Q06"]["question"],
        )

        self.assertEqual(outcome.status, "failed")
        self.assertEqual(outcome.error_stage, "model_response")
        self.assertEqual(
            [call.tool_name for call in outcome.tool_calls],
            ["analyze_time_trend"],
        )
        self.assertIn("frozen semantics", outcome.error_message)
        self.assertEqual(outcome.model_response_count, 2)
        self.assertEqual(len(outcome.raw_responses), 2)
        self.assertTrue(
            all(response.get("offline_mock") for response in outcome.raw_responses)
        )

    def test_revision_prompts_do_not_restore_recipe_routing(self) -> None:
        prompts = load_native_tool_agent_prompts_v2_1_revision()
        combined = f"{prompts.system.content}\n{prompts.report.content}"
        self.assertIn("全部七个白名单工具", combined)
        self.assertIn("程序不会预先替你选择工具", combined)
        self.assertNotIn("analysis_recipe", combined)
        self.assertNotIn("RECIPE-", combined)


if __name__ == "__main__":
    unittest.main()
