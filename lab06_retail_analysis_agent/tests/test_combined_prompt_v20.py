from __future__ import annotations

import unittest
import tempfile
from pathlib import Path

from src.online_native_tool_candidate_combined_v20 import PROMPT_PATH
from src.combined_prompt_v20_real_runner import (
    execute_validation_v20_checkpoint, execute_validation_v20_full,
)
from src.deepseek_internal_call_isolation_transport_mock_v2_3_4_2 import (
    CallIsolatedFrozenQuestionNativeToolMockClient,
    CallIsolatedLogicalClientV2_3_4_2, OfflineDeepSeekProviderV2_3_4_2,
)
from src.mock_h2_registry import FrozenH2MockRegistry
from src.tool_routing_prompt_v1_real_runner import OFFLINE_CONFIRMATION, validate_offline_request


class CombinedPromptV20Tests(unittest.TestCase):
    def test_prompt_disambiguates_local_incomplete_period_fact(self) -> None:
        text = PROMPT_PATH.read_text(encoding="utf-8")
        self.assertIn("local FACT evidence whose metric is incomplete_period", text)
        self.assertIn("must explicitly state that FACT value", text)
        self.assertIn("prohibition applies only when SLOT-002 lacks local evidence", text)

    def test_checkpoint_and_full_mock_runs_pass(self) -> None:
        authority = validate_offline_request(confirmation=OFFLINE_CONFIRMATION)
        def factory(_question_id: str):
            logical = CallIsolatedLogicalClientV2_3_4_2(CallIsolatedFrozenQuestionNativeToolMockClient())
            return OfflineDeepSeekProviderV2_3_4_2(logical)
        common = {"registry": FrozenH2MockRegistry(), "transport_factory": factory, "authority": authority}
        with tempfile.TemporaryDirectory() as temp:
            checkpoint = execute_validation_v20_checkpoint(
                api_key="offline-v20-checkpoint", output_parent=Path(temp),
                run_id="v20_checkpoint_offline", **common,
            )
            full = execute_validation_v20_full(
                api_key="offline-v20-full", output_parent=Path(temp),
                run_id="v20_full_offline", **common,
            )
        self.assertTrue(checkpoint.passed, checkpoint.summary)
        self.assertTrue(full.passed, full.summary)


if __name__ == "__main__":
    unittest.main()
