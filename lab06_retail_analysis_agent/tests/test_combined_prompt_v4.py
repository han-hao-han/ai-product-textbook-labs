from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.agent_orchestrator import _runtime_system_prompt
from src.combined_prompt_v4_real_runner import (
    QUESTION_ORDER,
    RESPONSE_CAP,
    execute_validation_v4,
)
from src.deepseek_internal_call_isolation_transport_mock_v2_3_4_2 import (
    CallIsolatedFrozenQuestionNativeToolMockClient,
    CallIsolatedLogicalClientV2_3_4_2,
    OfflineDeepSeekProviderV2_3_4_2,
)
from src.mock_h2_registry import FrozenH2MockRegistry
from src.online_native_tool_candidate_combined_v3 import (
    REPORT_PROMPT_PATH as REPORT_V3_PATH,
)
from src.online_native_tool_candidate_combined_v4 import (
    COMBINED_PROMPT_VERSION,
    REPORT_PROMPT_PATH,
    TOOL_ROUTING_PROMPT_PATH,
    project_runtime_messages_combined_v4,
)
from src.online_native_tool_candidate_tool_routing_v2 import (
    TOOL_ROUTING_PROMPT_PATH as TOOL_V2_PATH,
)
from src.prompt_contract import load_native_tool_agent_prompts_evidence_guard_v1
from src.tool_routing_prompt_v1_real_runner import (
    OFFLINE_CONFIRMATION,
    validate_offline_request,
)


class CombinedPromptV4Tests(unittest.TestCase):
    def test_both_prompts_are_additive(self) -> None:
        tool_v2 = TOOL_V2_PATH.read_text(encoding="utf-8").strip()
        tool_v3 = TOOL_ROUTING_PROMPT_PATH.read_text(encoding="utf-8").strip()
        report_v3 = REPORT_V3_PATH.read_text(encoding="utf-8").strip()
        report_v4 = REPORT_PROMPT_PATH.read_text(encoding="utf-8").strip()
        self.assertTrue(tool_v3.startswith(tool_v2))
        self.assertTrue(report_v4.startswith(report_v3))
        for marker in (
            "[TOOL-ROUTE-06]", "[TOOL-ROUTE-07]",
            "[CONTROL-SEMANTICS-01]", "[CONTROL-SEMANTICS-02]",
            "[CONTROL-SEMANTICS-03]",
        ):
            self.assertEqual(tool_v3.count(marker), 1)
        for marker in (
            "[PROMPT-EVIDENCE-06]", "[PROMPT-EVIDENCE-07]",
            "[PROMPT-EVIDENCE-08]", "[PROMPT-EVIDENCE-09]",
        ):
            self.assertEqual(report_v4.count(marker), 1)

    def test_runtime_projection_contains_v4_rules(self) -> None:
        prompts = load_native_tool_agent_prompts_evidence_guard_v1()
        runtime = _runtime_system_prompt(
            prompts,
            session_id="SESSION-combined-v4-test",
            turn_id="TURN-001",
        )
        content = project_runtime_messages_combined_v4(
            [{"role": "system", "content": runtime}]
        )[0]["content"]
        self.assertIn("[TOOL-ROUTE-07]", content)
        self.assertIn("[CONTROL-SEMANTICS-03]", content)
        self.assertIn("[PROMPT-EVIDENCE-09]", content)
        self.assertNotIn('"call_id"', content)

    def test_failed_question_checkpoint_passes_offline(self) -> None:
        authority = validate_offline_request(confirmation=OFFLINE_CONFIRMATION)

        def transport_factory(_question_id: str):
            logical = CallIsolatedLogicalClientV2_3_4_2(
                CallIsolatedFrozenQuestionNativeToolMockClient()
            )
            return OfflineDeepSeekProviderV2_3_4_2(logical)

        with tempfile.TemporaryDirectory() as temp:
            result = execute_validation_v4(
                api_key="offline-combined-v4-key",
                registry=FrozenH2MockRegistry(),
                transport_factory=transport_factory,
                authority=authority,
                output_parent=Path(temp),
                run_id="combined_prompt_v4_failed_offline_runner_test",
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
