from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.deepseek_internal_call_isolation_transport_mock_v2_3_4_2 import (
    CallIsolatedFrozenQuestionNativeToolMockClient,
    CallIsolatedLogicalClientV2_3_4_2,
    OfflineDeepSeekProviderV2_3_4_2,
)
from src.mock_h2_registry import FrozenH2MockRegistry
from src.online_native_tool_candidate_tool_routing_v1 import (
    TOOL_ROUTING_PROMPT_PATH as V1_PROMPT_PATH,
)
from src.online_native_tool_candidate_tool_routing_v2 import (
    TOOL_ROUTING_PROMPT_PATH,
)
from src.tool_routing_prompt_v1_real_runner import (
    OFFLINE_CONFIRMATION,
    validate_offline_request,
)
from src.tool_routing_prompt_v2_real_runner import execute_validation_v2


class ToolRoutingPromptV2Tests(unittest.TestCase):
    def test_v2_is_additive_and_reinforces_sequential_overview_routing(self) -> None:
        predecessor = V1_PROMPT_PATH.read_text(encoding="utf-8").strip()
        candidate = TOOL_ROUTING_PROMPT_PATH.read_text(encoding="utf-8").strip()
        self.assertTrue(candidate.startswith(predecessor))
        self.assertEqual(candidate.count("[TOOL-ROUTE-04]"), 1)
        self.assertEqual(candidate.count("[TOOL-ROUTE-05]"), 1)
        self.assertIn("绝不能在同一个响应中", candidate)
        self.assertIn("只调用 `get_sales_overview`", candidate)

    def test_v2_q02_first_offline_batch_passes_all_questions(self) -> None:
        authority = validate_offline_request(
            confirmation=OFFLINE_CONFIRMATION
        )

        def transport_factory(_question_id: str):
            logical = CallIsolatedLogicalClientV2_3_4_2(
                CallIsolatedFrozenQuestionNativeToolMockClient()
            )
            return OfflineDeepSeekProviderV2_3_4_2(logical)

        with tempfile.TemporaryDirectory() as temp:
            result = execute_validation_v2(
                api_key="offline-tool-routing-v2-key",
                registry=FrozenH2MockRegistry(),
                transport_factory=transport_factory,
                authority=authority,
                output_parent=Path(temp),
                run_id="tool_routing_prompt_v2_offline_runner_test",
            )
            self.assertTrue(result.passed, result.summary)
            self.assertEqual(len(result.summary["question_ids_executed"]), 10)
            self.assertEqual(result.summary["actual_response_attempts"], 27)
            self.assertEqual(
                result.summary["tool_selection_prompt_version"],
                "1.5.6-h3-native-tool-routing-v2",
            )


if __name__ == "__main__":
    unittest.main()
