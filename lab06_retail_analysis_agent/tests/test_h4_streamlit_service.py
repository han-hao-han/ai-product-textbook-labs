from __future__ import annotations

import unittest

from src.claim_level_report_controller_mock_v3_1 import ClaimTemplateLogicalClientV3_1
from src.conversation_state import EffectiveConditions
from src.deepseek_internal_call_isolation_transport_mock_v2_3_4_2 import (
    CallIsolatedFrozenQuestionNativeToolMockClient,
    OfflineDeepSeekProviderV2_3_4_2,
)
from src.fixed_question_validation import load_frozen_questions
from src.h4_streamlit_service import (
    build_download_zip,
    build_session_record,
    compose_session_question,
    mode_policy,
    run_manual_tool,
    run_online_turn,
)
from src.mock_h2_registry import FrozenH2MockRegistry


def _provider():
    logical = ClaimTemplateLogicalClientV3_1(
        CallIsolatedFrozenQuestionNativeToolMockClient()
    )
    return OfflineDeepSeekProviderV2_3_4_2(logical)


class H4StreamlitServiceTests(unittest.TestCase):
    def test_no_key_exposes_only_tool_layer_experience(self) -> None:
        policy = mode_policy(None)
        self.assertEqual(policy.user_visible_label, "工具层体验")
        self.assertFalse(policy.may_claim_agent_behavior)
        self.assertIn("model_tool_selection", policy.disabled)

    def test_manual_tool_uses_schema_fact_and_chart_without_model(self) -> None:
        result = run_manual_tool(
            registry=FrozenH2MockRegistry(),
            session_id="SESSION-h4-offline",
            turn_id="TURN-001",
            tool_name="rank_products",
            arguments={
                "period": "all_data",
                "start_date": None,
                "end_date": None,
                "metric": "sales_amount",
                "top_n": 5,
            },
        )
        self.assertEqual(result.result["tool_name"], "rank_products")
        self.assertEqual(len(result.facts), 16)
        self.assertIsNotNone(result.chart)
        self.assertEqual(result.chart.source_tool, "rank_products")

    def test_q02_mock_runs_v31_and_builds_privacy_checked_export(self) -> None:
        questions = load_frozen_questions()
        item = run_online_turn(
            api_key="offline-h4-test-key",
            registry=FrozenH2MockRegistry(),
            session_id="SESSION-h4-q02",
            turn_id="TURN-001",
            displayed_question=questions["Q02"]["question"],
            previous_conditions=EffectiveConditions.empty(),
            inherit_previous=False,
            question_id="Q02",
            transport=_provider(),
        )
        self.assertEqual(item.outcome.status, "completed")
        self.assertEqual(
            item.validation.status,
            "passed_deterministic_pending_manual_review",
        )
        self.assertEqual(item.outcome.tool_calls[0].tool_name, "rank_products")
        record = build_session_record([item])
        archive = build_download_zip(record, "TURN-001")
        self.assertGreater(len(archive), 1000)
        self.assertNotIn(b"CustomerID", archive)

    def test_session_context_does_not_copy_historical_facts(self) -> None:
        previous = EffectiveConditions(
            time_range={"mode": "all_data", "start_date": None, "end_date": None},
            metric="sales_amount",
            analysis_object="product",
            comparison_objects=None,
            filters=None,
            top_n=5,
        )
        text = compose_session_question(
            "继续分析",
            previous,
            inherit_previous=True,
        )
        self.assertIn("有效条件", text)
        self.assertNotIn("FACT-", text)
        self.assertEqual(
            compose_session_question(
                "继续分析", previous, inherit_previous=False
            ),
            "继续分析",
        )

    def test_inherited_conditions_preserve_frozen_question_terminal_protocol(self) -> None:
        questions = load_frozen_questions()
        previous = EffectiveConditions(
            time_range={"mode": "complete_months_only", "start_date": None, "end_date": None},
            metric="sales_quantity",
            analysis_object="time",
            comparison_objects=None,
            filters=None,
            top_n=None,
        )
        item = run_online_turn(
            api_key="offline-h4-test-key",
            registry=FrozenH2MockRegistry(),
            session_id="SESSION-h4-inherit",
            turn_id="TURN-002",
            displayed_question=questions["Q02"]["question"],
            previous_conditions=previous,
            inherit_previous=True,
            question_id="Q02",
            transport=_provider(),
        )
        self.assertEqual(item.outcome.status, "completed")
        self.assertEqual(item.submitted_question, questions["Q02"]["question"])
        self.assertIsNone(item.validation)
        self.assertNotIn("FACT-", item.submitted_question)


if __name__ == "__main__":
    unittest.main()
