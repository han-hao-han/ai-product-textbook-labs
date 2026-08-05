from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.combined_prompt_v8_real_runner import (
    RESPONSE_CAP,
    execute_validation_v8,
)
from src.combined_prompt_v8_full_real_runner import (
    RESPONSE_CAP as FULL_RESPONSE_CAP,
    execute_validation_v8_full,
)
from src.deepseek_internal_call_isolation_transport_mock_v2_3_4_2 import (
    CallIsolatedFrozenQuestionNativeToolMockClient,
    CallIsolatedLogicalClientV2_3_4_2,
    OfflineDeepSeekProviderV2_3_4_2,
)
from src.mock_h2_registry import FrozenH2MockRegistry
from src.online_native_tool_candidate_combined_v8 import COMBINED_PROMPT_VERSION
from src.terminal_summary_coverage_v8 import TERMINAL_SUMMARY_PROMPT_PATH
from src.tool_routing_prompt_v1_real_runner import (
    OFFLINE_CONFIRMATION,
    validate_offline_request,
)


class CombinedPromptV8Tests(unittest.TestCase):
    def test_terminal_instruction_is_bounded_for_largest_summary_set(self) -> None:
        template = TERMINAL_SUMMARY_PROMPT_PATH.read_text(
            encoding="utf-8"
        ).strip()
        instruction = template.replace(
            "{{REQUIRED_FACT_IDS}}",
            ",".join(f"FACT-{index:03d}" for index in range(1, 18)),
        )
        self.assertLessEqual(len(instruction), 1200)
        self.assertIn("Keep incomplete_period in its own claim", instruction)
        self.assertIn("never repeat it in peak", instruction)

    def test_q04_checkpoint_passes_offline(self) -> None:
        authority = validate_offline_request(confirmation=OFFLINE_CONFIRMATION)

        def transport_factory(_question_id: str):
            logical = CallIsolatedLogicalClientV2_3_4_2(
                CallIsolatedFrozenQuestionNativeToolMockClient()
            )
            return OfflineDeepSeekProviderV2_3_4_2(logical)

        with tempfile.TemporaryDirectory() as temp:
            result = execute_validation_v8(
                api_key="offline-combined-v8-key",
                registry=FrozenH2MockRegistry(),
                transport_factory=transport_factory,
                authority=authority,
                output_parent=Path(temp),
                run_id="combined_prompt_v8_q04_offline_runner_test",
            )
            self.assertTrue(result.passed, result.summary)
            self.assertEqual(result.summary["question_ids_executed"], ["Q04"])
            self.assertEqual(result.summary["actual_response_attempts"], RESPONSE_CAP)
            self.assertEqual(
                result.summary["tool_selection_prompt_version"],
                COMBINED_PROMPT_VERSION,
            )

    def test_q01_q10_final_runner_passes_offline(self) -> None:
        authority = validate_offline_request(confirmation=OFFLINE_CONFIRMATION)

        def transport_factory(_question_id: str):
            logical = CallIsolatedLogicalClientV2_3_4_2(
                CallIsolatedFrozenQuestionNativeToolMockClient()
            )
            return OfflineDeepSeekProviderV2_3_4_2(logical)

        with tempfile.TemporaryDirectory() as temp:
            result = execute_validation_v8_full(
                api_key="offline-combined-v8-full-key",
                registry=FrozenH2MockRegistry(),
                transport_factory=transport_factory,
                authority=authority,
                output_parent=Path(temp),
                run_id="combined_prompt_v8_full_offline_runner_test",
            )
            self.assertTrue(result.passed, result.summary)
            self.assertEqual(len(result.summary["question_ids_executed"]), 10)
            self.assertEqual(
                result.summary["actual_response_attempts"], FULL_RESPONSE_CAP
            )


if __name__ == "__main__":
    unittest.main()
