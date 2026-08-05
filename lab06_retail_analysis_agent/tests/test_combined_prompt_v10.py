from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.combined_prompt_v10_real_runner import (
    QUESTION_ORDER,
    RESPONSE_CAP,
    execute_validation_v10,
)
from src.deepseek_internal_call_isolation_transport_mock_v2_3_4_2 import (
    CallIsolatedFrozenQuestionNativeToolMockClient,
    CallIsolatedLogicalClientV2_3_4_2,
    OfflineDeepSeekProviderV2_3_4_2,
)
from src.fact_schema import FactDimension
from src.mock_h2_registry import FrozenH2MockRegistry
from src.online_native_tool_candidate_combined_v10 import COMBINED_PROMPT_VERSION
from src.report_validation import ReportFactReference
from src.terminal_claim_groups_v10 import (
    TERMINAL_CLAIM_GROUPS_PROMPT_PATH,
    required_claim_fact_groups_v10,
)
from src.tool_routing_prompt_v1_real_runner import (
    OFFLINE_CONFIRMATION,
    validate_offline_request,
)


def _fact(
    fact_id: str, metric: str, value: str, *, rank=None, dimensions=None,
) -> ReportFactReference:
    return ReportFactReference(
        fact_id=fact_id,
        metric=metric,
        value=value,
        display_value=value,
        unit="GBP" if metric == "sales_amount" else "calendar_month",
        rank=rank,
        dimensions=dimensions or [],
        period="complete_months_only",
        start_date=None,
        end_date=None,
    )


class CombinedPromptV10Tests(unittest.TestCase):
    def test_peak_and_ranked_sales_share_one_claim_group(self) -> None:
        month = [FactDimension(name="month", value="2011-11")]
        facts = [
            _fact("FACT-001", "peak_period", "2011-11", rank=1, dimensions=month),
            _fact("FACT-002", "sales_amount", "200", rank=1, dimensions=month),
            _fact("FACT-003", "sales_quantity", "50", dimensions=month),
            _fact("FACT-004", "incomplete_period", "2011-12"),
        ]
        self.assertEqual(
            required_claim_fact_groups_v10(facts),
            [["FACT-001", "FACT-002", "FACT-003"]],
        )

    def test_segments_are_separate_claim_groups(self) -> None:
        uk = [FactDimension(name="segment", value="united_kingdom")]
        other = [FactDimension(name="segment", value="outside_united_kingdom")]
        facts = [
            _fact("FACT-001", "sales_amount", "100", dimensions=uk),
            _fact("FACT-002", "sales_quantity", "10", dimensions=uk),
            _fact("FACT-003", "sales_amount", "20", dimensions=other),
            _fact("FACT-004", "sales_quantity", "2", dimensions=other),
        ]
        self.assertEqual(
            required_claim_fact_groups_v10(facts),
            [["FACT-001", "FACT-002"], ["FACT-003", "FACT-004"]],
        )

    def test_dynamic_instruction_stays_within_frozen_schema_capacity(self) -> None:
        template = TERMINAL_CLAIM_GROUPS_PROMPT_PATH.read_text(
            encoding="utf-8"
        ).strip()
        groups = "|".join(
            f"FACT-{index:03d}" for index in range(1, 18)
        )
        instruction = template.replace("{{CLAIM_FACT_GROUPS}}", groups)
        self.assertLessEqual(len(instruction), 1200)
        self.assertIn("exactly one claim per FACT group", instruction)

    def test_q04_q05_checkpoint_passes_offline(self) -> None:
        authority = validate_offline_request(confirmation=OFFLINE_CONFIRMATION)

        def transport_factory(_question_id: str):
            logical = CallIsolatedLogicalClientV2_3_4_2(
                CallIsolatedFrozenQuestionNativeToolMockClient()
            )
            return OfflineDeepSeekProviderV2_3_4_2(logical)

        with tempfile.TemporaryDirectory() as temp:
            result = execute_validation_v10(
                api_key="offline-combined-v10-key",
                registry=FrozenH2MockRegistry(),
                transport_factory=transport_factory,
                authority=authority,
                output_parent=Path(temp),
                run_id="combined_prompt_v10_q04_q05_offline_runner_test",
            )
            self.assertTrue(result.passed, result.summary)
            self.assertEqual(
                result.summary["question_ids_executed"], list(QUESTION_ORDER)
            )
            self.assertEqual(result.summary["actual_response_attempts"], RESPONSE_CAP)
            self.assertEqual(
                result.summary["tool_selection_prompt_version"],
                COMBINED_PROMPT_VERSION,
            )


if __name__ == "__main__":
    unittest.main()
