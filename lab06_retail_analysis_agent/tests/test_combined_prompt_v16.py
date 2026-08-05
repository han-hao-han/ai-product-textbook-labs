from __future__ import annotations

import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace

from src.fixed_question_validation import _statement_contains
from src.combined_prompt_v16_q07_real_runner import (
    RESPONSE_CAP,
    execute_validation_v16_q07,
)
from src.combined_prompt_v16_full_real_runner import (
    BASELINE_RESPONSE_COUNT,
    RESPONSE_CAP as FULL_RESPONSE_CAP,
    execute_validation_v16_full,
)
from src.deepseek_internal_call_isolation_transport_mock_v2_3_4_2 import (
    CallIsolatedFrozenQuestionNativeToolMockClient,
    CallIsolatedLogicalClientV2_3_4_2,
    OfflineDeepSeekProviderV2_3_4_2,
)
from src.mock_h2_registry import FrozenH2MockRegistry
from src.tool_routing_prompt_v1_real_runner import (
    EXPECTED_RESPONSES,
    OFFLINE_CONFIRMATION,
    validate_offline_request,
)
from src.terminal_fact_expression_v16 import terminal_fact_expression_issues_v16


class CombinedPromptV16Tests(unittest.TestCase):
    def test_frozen_harness_keeps_exact_ratio_literal_rule(self) -> None:
        self.assertFalse(_statement_contains("销售行覆盖率为74.8159%。", 0.748159))
        self.assertFalse(_statement_contains("金额覆盖率83.5098%。", "0.835098"))
        self.assertFalse(_statement_contains("销售行覆盖率为74.8%。", 0.748159))

    def test_numeric_fact_evidence_must_be_expressed_in_local_claim(self) -> None:
        fact = SimpleNamespace(
            evidence_type="FACT",
            value="5152002",
            display_value="5,152,002",
            fact_id="FACT-009",
            metric="sales_quantity",
            rank=None,
            start_date=None,
            end_date=None,
            dimensions=[],
        )
        response = SimpleNamespace(
            report=SimpleNamespace(
                sections=[SimpleNamespace(claims=[SimpleNamespace(
                    statement="已知客户子集的其他指标见证据。", evidence=[fact]
                )])]
            )
        )
        issues = terminal_fact_expression_issues_v16(response)
        self.assertEqual([item["code"] for item in issues], [
            "fact_value_not_expressed"
        ])
        self.assertEqual(issues[0]["fact_id"], "FACT-009")

    def test_fact_display_value_satisfies_local_expression(self) -> None:
        fact = SimpleNamespace(
            evidence_type="FACT",
            value="0.748159",
            display_value="74.8159%",
            fact_id="FACT-013",
            metric="sales_row_coverage",
            rank=None,
            start_date=None,
            end_date=None,
            dimensions=[],
        )
        response = SimpleNamespace(
            report=SimpleNamespace(
                sections=[SimpleNamespace(claims=[SimpleNamespace(
                    statement="销售行覆盖率为74.8159%。", evidence=[fact]
                )])]
            )
        )
        self.assertEqual(terminal_fact_expression_issues_v16(response), [])

    def test_q07_offline_runner_passes_with_unused_allowances(self) -> None:
        authority = validate_offline_request(confirmation=OFFLINE_CONFIRMATION)

        def transport_factory(_question_id: str):
            logical = CallIsolatedLogicalClientV2_3_4_2(
                CallIsolatedFrozenQuestionNativeToolMockClient()
            )
            return OfflineDeepSeekProviderV2_3_4_2(logical)

        with tempfile.TemporaryDirectory() as temp:
            result = execute_validation_v16_q07(
                api_key="offline-combined-v16-q07-key",
                registry=FrozenH2MockRegistry(),
                transport_factory=transport_factory,
                authority=authority,
                output_parent=Path(temp),
                run_id="combined_prompt_v16_q07_offline_runner_test",
            )
            self.assertTrue(result.passed, result.summary)
            self.assertEqual(
                result.summary["actual_response_attempts"], EXPECTED_RESPONSES["Q07"]
            )
            self.assertEqual(result.summary["response_attempt_upper_bound"], RESPONSE_CAP)

    def test_q01_q10_offline_runner_passes_with_unused_allowances(self) -> None:
        authority = validate_offline_request(confirmation=OFFLINE_CONFIRMATION)

        def transport_factory(_question_id: str):
            logical = CallIsolatedLogicalClientV2_3_4_2(
                CallIsolatedFrozenQuestionNativeToolMockClient()
            )
            return OfflineDeepSeekProviderV2_3_4_2(logical)

        with tempfile.TemporaryDirectory() as temp:
            result = execute_validation_v16_full(
                api_key="offline-combined-v16-full-key",
                registry=FrozenH2MockRegistry(),
                transport_factory=transport_factory,
                authority=authority,
                output_parent=Path(temp),
                run_id="combined_prompt_v16_full_offline_runner_test",
            )
            self.assertTrue(result.passed, result.summary)
            self.assertEqual(
                result.summary["actual_response_attempts"], BASELINE_RESPONSE_COUNT
            )
            self.assertEqual(
                result.summary["response_attempt_upper_bound"], FULL_RESPONSE_CAP
            )


if __name__ == "__main__":
    unittest.main()
