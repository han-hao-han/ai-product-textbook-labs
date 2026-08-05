from __future__ import annotations

import unittest

from src.chat_runtime_mock_v1 import (
    ChatRuntimeLogicalClientV1,
    ScriptedChatRoutingClient,
)
from src.chat_runtime_v1 import GeneralChatClientAdapter
from src.conversation_state import EffectiveConditions
from src.deepseek_internal_call_isolation_transport_mock_v2_3_4_2 import (
    OfflineDeepSeekProviderV2_3_4_2,
)
from src.deepseek_client import ProviderToolCall
from src.fixed_question_validation import load_frozen_questions, validate_fixed_question
from src.h4_streamlit_service import run_chat_turn
from src.mock_h2_registry import FrozenH2MockRegistry


class ExtendedChatMockRegistry(FrozenH2MockRegistry):
    def _data(self, tool_name, arguments):
        if tool_name != "get_data_profile":
            return super()._data(tool_name, arguments)
        sections = {
            "summary": {
                "source_rows": 541909,
                "exact_duplicate_rows_after_first": 5268,
                "rows_after_keep_first": 536641,
                "sales_fact_rows": 524878,
                "exception_rows": 11763,
                "time_minimum": "2010-12-01T08:26:00",
                "time_maximum": "2011-12-09T12:50:00",
                "incomplete_periods": ["2011-12"],
            },
            "classification": {"sale": 524878, "cancelled": 8872},
            "customer_coverage": {
                "known_customer_rows": 392692,
                "customer_count": 4338,
                "sales_row_coverage": 0.748067,
                "sales_amount_coverage": 0.835098,
            },
        }
        section = arguments["section"]
        return sections if section == "all" else {section: sections[section]}


def _provider(
    *,
    steps,
    require_clarification=False,
    batch_first_response=False,
    repeat_batch_while_incomplete=False,
):
    routing = ScriptedChatRoutingClient(
        steps=list(steps),
        require_clarification=require_clarification,
        batch_first_response=batch_first_response,
        repeat_batch_while_incomplete=repeat_batch_while_incomplete,
    )
    logical = ChatRuntimeLogicalClientV1(delegate=routing)
    return OfflineDeepSeekProviderV2_3_4_2(logical)


RANK_ARGUMENTS = {
    "period": "all_data",
    "start_date": "__NONE__",
    "end_date": "__NONE__",
    "metric": "sales_amount",
    "top_n": 5,
}
SEGMENT_ARGUMENTS = {
    "period": "complete_months_only",
    "start_date": "__NONE__",
    "end_date": "__NONE__",
    "comparison": "united_kingdom_vs_other",
}
OVERVIEW_ARGUMENTS = {
    "period": "all_data",
    "start_date": "__NONE__",
    "end_date": "__NONE__",
    "include_incomplete_period_warning": True,
}
CUSTOMER_ARGUMENTS = {
    "period": "all_data",
    "start_date": "null",
    "end_date": "null",
    "include_coverage": True,
}


class ChatRuntimeV1Tests(unittest.TestCase):
    def test_chat_null_string_date_normalization_is_narrow(self) -> None:
        noncustom = GeneralChatClientAdapter._normalize_chat_arguments(
            ProviderToolCall(
                provider_call_id="provider-null-001",
                tool_name="analyze_customers",
                arguments=CUSTOMER_ARGUMENTS,
            )
        )
        self.assertIsNone(noncustom["start_date"])
        self.assertIsNone(noncustom["end_date"])

        custom = GeneralChatClientAdapter._normalize_chat_arguments(
            ProviderToolCall(
                provider_call_id="provider-null-002",
                tool_name="analyze_customers",
                arguments={
                    **CUSTOMER_ARGUMENTS,
                    "period": "custom",
                },
            )
        )
        self.assertEqual(custom["start_date"], "null")
        self.assertEqual(custom["end_date"], "null")

    def test_arbitrary_supported_question_uses_native_tool_and_v31_report(self) -> None:
        item = run_chat_turn(
            api_key="offline-chat-key",
            registry=FrozenH2MockRegistry(),
            session_id="SESSION-chat-free",
            turn_id="TURN-001",
            question="请列出销售额最高的5个商品，并说明主要结果。",
            previous_conditions=EffectiveConditions.empty(),
            inherit_previous=False,
            transport=_provider(steps=[("rank_products", RANK_ARGUMENTS)]),
        )
        self.assertEqual(item.runtime_kind, "general_chat_v1")
        self.assertEqual(item.outcome.status, "completed")
        self.assertEqual(item.outcome.tool_calls[0].tool_name, "rank_products")
        self.assertIn("受控证据", item.outcome.report_markdown)
        self.assertEqual(item.response_attempted, 4)
        self.assertTrue(
            any(trace.action == "v3_1_report_finalized" for trace in item.trace)
        )

    def test_q08_clarification_resumes_same_turn_after_user_answer(self) -> None:
        question = load_frozen_questions()["Q08"]["question"]
        pending = run_chat_turn(
            api_key="offline-chat-key",
            registry=FrozenH2MockRegistry(),
            session_id="SESSION-chat-q08",
            turn_id="TURN-001",
            question=question,
            previous_conditions=EffectiveConditions.empty(),
            inherit_previous=False,
            transport=_provider(steps=[], require_clarification=True),
        )
        self.assertEqual(pending.outcome.status, "needs_clarification")
        self.assertEqual(pending.response_attempted, 1)

        completed = run_chat_turn(
            api_key="offline-chat-key",
            registry=FrozenH2MockRegistry(),
            session_id="SESSION-chat-q08",
            turn_id="TURN-001",
            question=question,
            previous_conditions=EffectiveConditions.empty(),
            inherit_previous=False,
            clarification_answer="比较完整月份的销售额，比较英国与英国以外。",
            pending_experience=pending,
            transport=_provider(
                steps=[("compare_segments", SEGMENT_ARGUMENTS)],
                require_clarification=True,
            ),
        )
        self.assertEqual(completed.outcome.status, "completed")
        self.assertEqual(completed.outcome.turn_id, pending.outcome.turn_id)
        self.assertEqual(completed.outcome.tool_calls[0].tool_name, "compare_segments")
        self.assertEqual(completed.response_attempted, 5)
        self.assertEqual(
            completed.clarification_answer,
            "比较完整月份的销售额，比较英国与英国以外。",
        )
        self.assertIsNotNone(completed.clarification_message)

    def test_fixed_q02_remains_compatible_with_frozen_harness(self) -> None:
        question = load_frozen_questions()["Q02"]["question"]
        item = run_chat_turn(
            api_key="offline-chat-key",
            registry=FrozenH2MockRegistry(),
            session_id="SESSION-chat-q02",
            turn_id="TURN-001",
            question=question,
            previous_conditions=EffectiveConditions.empty(),
            inherit_previous=False,
            transport=_provider(steps=[("rank_products", RANK_ARGUMENTS)]),
        )
        result = validate_fixed_question("Q02", item.outcome)
        self.assertEqual(
            result.status,
            "passed_deterministic_pending_manual_review",
        )

    def test_q07_batched_provider_calls_are_serialized_and_both_executed(self) -> None:
        question = load_frozen_questions()["Q07"]["question"]
        item = run_chat_turn(
            api_key="offline-chat-key",
            registry=FrozenH2MockRegistry(),
            session_id="SESSION-chat-q05-batch",
            turn_id="TURN-001",
            question=question,
            previous_conditions=EffectiveConditions.empty(),
            inherit_previous=False,
            transport=_provider(
                steps=[
                    ("get_sales_overview", OVERVIEW_ARGUMENTS),
                    ("analyze_customers", CUSTOMER_ARGUMENTS),
                ],
                batch_first_response=True,
                repeat_batch_while_incomplete=True,
            ),
        )
        self.assertEqual(item.outcome.status, "completed")
        self.assertEqual(
            [call.tool_name for call in item.outcome.tool_calls],
            ["get_sales_overview", "analyze_customers"],
        )
        self.assertEqual(item.response_attempted, 5)
        self.assertEqual(item.trace[0].action, "batched_tool_calls_replanned")
        self.assertEqual(item.trace[1].action, "batched_tool_calls_replanned")
        validation = validate_fixed_question("Q07", item.outcome)
        self.assertEqual(
            validation.status,
            "passed_deterministic_pending_manual_review",
            validation.model_dump(mode="json"),
        )

    def test_general_chat_allows_five_progressive_tool_calls(self) -> None:
        question = load_frozen_questions()["Q07"]["question"]
        item = run_chat_turn(
            api_key="offline-chat-key",
            registry=ExtendedChatMockRegistry(),
            session_id="SESSION-chat-five-tools",
            turn_id="TURN-001",
            question=question,
            previous_conditions=EffectiveConditions.empty(),
            inherit_previous=False,
            transport=_provider(
                steps=[
                    ("get_sales_overview", OVERVIEW_ARGUMENTS),
                    ("analyze_customers", CUSTOMER_ARGUMENTS),
                    ("get_data_profile", {"section": "summary"}),
                    ("get_data_profile", {"section": "customer_coverage"}),
                    ("get_data_profile", {"section": "classification"}),
                ],
            ),
        )
        self.assertEqual(item.outcome.status, "completed")
        self.assertEqual(len(item.outcome.tool_calls), 5)
        self.assertEqual(item.response_attempted, 8)
        self.assertEqual(item.response_limit, 12)
        self.assertEqual(item.outcome.report_validation.status, "passed")

    def test_tool_and_response_limits_reset_for_each_new_turn(self) -> None:
        items = []
        for turn_id in ("TURN-001", "TURN-002"):
            items.append(
                run_chat_turn(
                    api_key="offline-chat-key",
                    registry=FrozenH2MockRegistry(),
                    session_id="SESSION-chat-unbounded-turns",
                    turn_id=turn_id,
                    question="请列出销售额最高的5个商品。",
                    previous_conditions=EffectiveConditions.empty(),
                    inherit_previous=False,
                    transport=_provider(
                        steps=[("rank_products", RANK_ARGUMENTS)]
                    ),
                )
            )
        self.assertEqual([item.response_limit for item in items], [12, 12])
        self.assertEqual([item.response_attempted for item in items], [4, 4])
        self.assertTrue(all(item.outcome.status == "completed" for item in items))


if __name__ == "__main__":
    unittest.main()
