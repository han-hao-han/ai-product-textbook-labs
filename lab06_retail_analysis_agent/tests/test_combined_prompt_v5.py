from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.agent_orchestrator import _runtime_system_prompt
from src.combined_prompt_v5_real_runner import (
    QUESTION_ORDER,
    RESPONSE_CAP,
    execute_validation_v5,
)
from src.deepseek_internal_call_isolation_transport_mock_v2_3_4_2 import (
    CallIsolatedFrozenQuestionNativeToolMockClient,
    CallIsolatedLogicalClientV2_3_4_2,
    OfflineDeepSeekProviderV2_3_4_2,
)
from src.mock_h2_registry import FrozenH2MockRegistry
from src.online_native_tool_candidate_combined_v4 import (
    REPORT_PROMPT_PATH as REPORT_V4_PATH,
)
from src.online_native_tool_candidate_combined_v5 import (
    COMBINED_PROMPT_VERSION,
    REPORT_PROMPT_PATH,
    project_runtime_messages_combined_v5,
)
from src.prompt_contract import load_native_tool_agent_prompts_evidence_guard_v1
from src.tool_routing_prompt_v1_real_runner import (
    OFFLINE_CONFIRMATION,
    validate_offline_request,
)


class CombinedPromptV5Tests(unittest.TestCase):
    def test_report_prompt_is_additive(self) -> None:
        predecessor = REPORT_V4_PATH.read_text(encoding="utf-8").strip()
        candidate = REPORT_PROMPT_PATH.read_text(encoding="utf-8").strip()
        self.assertTrue(candidate.startswith(predecessor))
        for marker in (
            "[PROMPT-EVIDENCE-10]", "[PROMPT-EVIDENCE-11]",
            "[PROMPT-EVIDENCE-12]", "[PROMPT-EVIDENCE-13]",
        ):
            self.assertEqual(candidate.count(marker), 1)

    def test_runtime_projection_contains_v5_rules(self) -> None:
        prompts = load_native_tool_agent_prompts_evidence_guard_v1()
        runtime = _runtime_system_prompt(
            prompts,
            session_id="SESSION-combined-v5-test",
            turn_id="TURN-001",
        )
        content = project_runtime_messages_combined_v5(
            [{"role": "system", "content": runtime}]
        )[0]["content"]
        self.assertIn("[TOOL-ROUTE-07]", content)
        self.assertIn("[PROMPT-EVIDENCE-13]", content)
        self.assertNotIn('"call_id"', content)

    def test_four_question_checkpoint_passes_offline(self) -> None:
        authority = validate_offline_request(confirmation=OFFLINE_CONFIRMATION)

        def transport_factory(_question_id: str):
            logical = CallIsolatedLogicalClientV2_3_4_2(
                CallIsolatedFrozenQuestionNativeToolMockClient()
            )
            return OfflineDeepSeekProviderV2_3_4_2(logical)

        with tempfile.TemporaryDirectory() as temp:
            result = execute_validation_v5(
                api_key="offline-combined-v5-key",
                registry=FrozenH2MockRegistry(),
                transport_factory=transport_factory,
                authority=authority,
                output_parent=Path(temp),
                run_id="combined_prompt_v5_four_q_offline_runner_test",
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
