from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.combined_prompt_v6_real_runner import (
    QUESTION_ORDER,
    RESPONSE_CAP,
    execute_validation_v6,
)
from src.deepseek_internal_call_isolation_transport_mock_v2_3_4_2 import (
    CallIsolatedFrozenQuestionNativeToolMockClient,
    CallIsolatedLogicalClientV2_3_4_2,
    OfflineDeepSeekProviderV2_3_4_2,
)
from src.mock_h2_registry import FrozenH2MockRegistry
from src.online_native_tool_candidate_combined_v6 import (
    COMBINED_PROMPT_VERSION,
    NativeToolOnlineCandidateCombinedV6,
)
from src.terminal_coverage_guidance_v6 import (
    TERMINAL_COVERAGE_PROMPT_PATH,
    project_terminal_context_v6,
)
from src.tool_routing_prompt_v1_real_runner import (
    OFFLINE_CONFIRMATION,
    validate_offline_request,
)


class CombinedPromptV6Tests(unittest.TestCase):
    def test_terminal_instruction_is_bounded_and_has_coverage_rules(self) -> None:
        instruction = TERMINAL_COVERAGE_PROMPT_PATH.read_text(
            encoding="utf-8"
        ).strip()
        self.assertLessEqual(len(instruction), 1200)
        self.assertIn("SLOT-002 must cover every distinct FACT", instruction)
        self.assertIn("at most 12 claims", instruction)
        self.assertIn("write both value and display_value", instruction)
        self.assertNotIn("call_id", instruction)

    def test_v6_candidate_wires_terminal_context_projector(self) -> None:
        logical = CallIsolatedLogicalClientV2_3_4_2(
            CallIsolatedFrozenQuestionNativeToolMockClient()
        )
        candidate = NativeToolOnlineCandidateCombinedV6(
            api_key="offline-v6-wire-key",
            registry=FrozenH2MockRegistry(),
            response_limit=3,
            transport=OfflineDeepSeekProviderV2_3_4_2(logical),
        )
        self.assertIs(candidate.client.terminal_context_projector, project_terminal_context_v6)

    def test_four_question_checkpoint_passes_offline(self) -> None:
        authority = validate_offline_request(confirmation=OFFLINE_CONFIRMATION)

        def transport_factory(_question_id: str):
            logical = CallIsolatedLogicalClientV2_3_4_2(
                CallIsolatedFrozenQuestionNativeToolMockClient()
            )
            return OfflineDeepSeekProviderV2_3_4_2(logical)

        with tempfile.TemporaryDirectory() as temp:
            result = execute_validation_v6(
                api_key="offline-combined-v6-key",
                registry=FrozenH2MockRegistry(),
                transport_factory=transport_factory,
                authority=authority,
                output_parent=Path(temp),
                run_id="combined_prompt_v6_four_q_offline_runner_test",
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
