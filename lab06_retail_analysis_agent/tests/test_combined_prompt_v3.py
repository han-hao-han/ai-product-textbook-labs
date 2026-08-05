from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.agent_orchestrator import _runtime_system_prompt
from src.combined_prompt_v3_real_runner import execute_validation_v3
from src.deepseek_internal_call_isolation_transport_mock_v2_3_4_2 import (
    CallIsolatedFrozenQuestionNativeToolMockClient,
    CallIsolatedLogicalClientV2_3_4_2,
    OfflineDeepSeekProviderV2_3_4_2,
)
from src.mock_h2_registry import FrozenH2MockRegistry
from src.online_native_tool_candidate_combined_v3 import (
    COMBINED_PROMPT_VERSION,
    REPORT_PREDECESSOR_PATH,
    REPORT_PROMPT_PATH,
    project_runtime_messages_combined_v3,
)
from src.prompt_contract import load_native_tool_agent_prompts_evidence_guard_v1
from src.tool_routing_prompt_v1_real_runner import (
    OFFLINE_CONFIRMATION,
    validate_offline_request,
)


class CombinedPromptV3Tests(unittest.TestCase):
    def test_report_prompt_is_additive_and_has_metric_binding_rules(self) -> None:
        predecessor = REPORT_PREDECESSOR_PATH.read_text(encoding="utf-8").strip()
        candidate = REPORT_PROMPT_PATH.read_text(encoding="utf-8").strip()
        self.assertTrue(candidate.startswith(predecessor))
        self.assertEqual(candidate.count("[PROMPT-EVIDENCE-04]"), 1)
        self.assertEqual(candidate.count("[PROMPT-EVIDENCE-05]"), 1)

    def test_runtime_projection_contains_both_versioned_prompt_boundaries(self) -> None:
        prompts = load_native_tool_agent_prompts_evidence_guard_v1()
        runtime = _runtime_system_prompt(
            prompts,
            session_id="SESSION-combined-v3-test",
            turn_id="TURN-001",
        )
        projected = project_runtime_messages_combined_v3(
            [{"role": "system", "content": runtime}]
        )
        content = projected[0]["content"]
        self.assertIn("[TOOL-ROUTE-05]", content)
        self.assertIn("[PROMPT-EVIDENCE-04]", content)
        self.assertIn("[PROMPT-EVIDENCE-05]", content)
        self.assertNotIn('"call_id"', content)

    def test_combined_prompt_q01_q10_offline_batch_passes(self) -> None:
        authority = validate_offline_request(confirmation=OFFLINE_CONFIRMATION)

        def transport_factory(_question_id: str):
            logical = CallIsolatedLogicalClientV2_3_4_2(
                CallIsolatedFrozenQuestionNativeToolMockClient()
            )
            return OfflineDeepSeekProviderV2_3_4_2(logical)

        with tempfile.TemporaryDirectory() as temp:
            result = execute_validation_v3(
                api_key="offline-combined-v3-key",
                registry=FrozenH2MockRegistry(),
                transport_factory=transport_factory,
                authority=authority,
                output_parent=Path(temp),
                run_id="combined_prompt_v3_offline_runner_test",
            )
            self.assertTrue(result.passed, result.summary)
            self.assertEqual(len(result.summary["question_ids_executed"]), 10)
            self.assertEqual(result.summary["actual_response_attempts"], 27)
            self.assertTrue(result.summary["continue_after_failure"])
            self.assertEqual(
                result.summary["tool_selection_prompt_version"],
                COMBINED_PROMPT_VERSION,
            )
            state = json.loads(
                (result.output_dir / "run_state.json").read_text(encoding="utf-8")
            )
            self.assertEqual(len(set(state["http_response_files"])), 27)
            self.assertEqual(len(set(state["parsed_response_files"])), 27)


if __name__ == "__main__":
    unittest.main()
