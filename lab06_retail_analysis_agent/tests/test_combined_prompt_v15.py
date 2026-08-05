from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.combined_prompt_v15_real_runner import (
    QUESTION_ORDER,
    RESPONSE_CAP,
    execute_validation_v15,
)
from src.combined_prompt_v15_full_real_runner import (
    BASELINE_RESPONSE_COUNT,
    QUESTION_ORDER as FULL_QUESTION_ORDER,
    RESPONSE_CAP as FULL_RESPONSE_CAP,
    execute_validation_v15_full,
)
from src.deepseek_internal_call_isolation_transport_mock_v2_3_4_2 import (
    CallIsolatedFrozenQuestionNativeToolMockClient,
    CallIsolatedLogicalClientV2_3_4_2,
    OfflineDeepSeekProviderV2_3_4_2,
)
from src.mock_h2_registry import FrozenH2MockRegistry
from src.online_native_tool_candidate_combined_v15 import COMBINED_PROMPT_VERSION
from src.terminal_evidence_completeness_v15 import terminal_evidence_issues_v15
from src.tool_routing_prompt_v1_real_runner import (
    EXPECTED_RESPONSES,
    OFFLINE_CONFIRMATION,
    validate_offline_request,
)


class CombinedPromptV15Tests(unittest.TestCase):
    def test_numeric_request_value_must_be_expressed_in_local_claim(self) -> None:
        request = SimpleNamespace(
            evidence_type="REQUEST",
            value="2011-12",
            request_id="REQUEST-002",
            parameter_name="excluded_period",
        )
        response = SimpleNamespace(
            report=SimpleNamespace(
                sections=[SimpleNamespace(claims=[SimpleNamespace(
                    statement="排除不完整期间。", evidence=[request]
                )])]
            )
        )
        issues = terminal_evidence_issues_v15(response)
        self.assertEqual([item["code"] for item in issues], [
            "request_value_not_expressed"
        ])
        self.assertEqual(issues[0]["required_literal"], "2011-12")

    def test_expressed_numeric_request_value_passes(self) -> None:
        request = SimpleNamespace(
            evidence_type="REQUEST",
            value="2011-12",
            request_id="REQUEST-002",
            parameter_name="excluded_period",
        )
        response = SimpleNamespace(
            report=SimpleNamespace(
                sections=[SimpleNamespace(claims=[SimpleNamespace(
                    statement="排除不完整期间2011-12。", evidence=[request]
                )])]
            )
        )
        self.assertEqual(terminal_evidence_issues_v15(response), [])

    def test_q04_offline_runner_keeps_bounded_allowance(self) -> None:
        authority = validate_offline_request(confirmation=OFFLINE_CONFIRMATION)

        def transport_factory(_question_id: str):
            logical = CallIsolatedLogicalClientV2_3_4_2(
                CallIsolatedFrozenQuestionNativeToolMockClient()
            )
            return OfflineDeepSeekProviderV2_3_4_2(logical)

        with tempfile.TemporaryDirectory() as temp:
            result = execute_validation_v15(
                api_key="offline-combined-v15-key",
                registry=FrozenH2MockRegistry(),
                transport_factory=transport_factory,
                authority=authority,
                output_parent=Path(temp),
                run_id="combined_prompt_v15_q04_offline_runner_test",
            )
            self.assertTrue(result.passed, result.summary)
            self.assertEqual(result.summary["question_ids_executed"], list(QUESTION_ORDER))
            self.assertEqual(
                result.summary["actual_response_attempts"], EXPECTED_RESPONSES["Q04"]
            )
            self.assertEqual(result.summary["response_attempt_upper_bound"], RESPONSE_CAP)
            self.assertEqual(result.summary["tool_selection_prompt_version"], COMBINED_PROMPT_VERSION)

    def test_q01_q10_offline_runner_passes_with_unused_allowances(self) -> None:
        authority = validate_offline_request(confirmation=OFFLINE_CONFIRMATION)

        def transport_factory(_question_id: str):
            logical = CallIsolatedLogicalClientV2_3_4_2(
                CallIsolatedFrozenQuestionNativeToolMockClient()
            )
            return OfflineDeepSeekProviderV2_3_4_2(logical)

        with tempfile.TemporaryDirectory() as temp:
            result = execute_validation_v15_full(
                api_key="offline-combined-v15-full-key",
                registry=FrozenH2MockRegistry(),
                transport_factory=transport_factory,
                authority=authority,
                output_parent=Path(temp),
                run_id="combined_prompt_v15_full_offline_runner_test",
            )
            self.assertTrue(result.passed, result.summary)
            self.assertEqual(
                result.summary["question_ids_executed"], list(FULL_QUESTION_ORDER)
            )
            self.assertEqual(
                result.summary["actual_response_attempts"], BASELINE_RESPONSE_COUNT
            )
            self.assertEqual(
                result.summary["response_attempt_upper_bound"], FULL_RESPONSE_CAP
            )


if __name__ == "__main__":
    unittest.main()
