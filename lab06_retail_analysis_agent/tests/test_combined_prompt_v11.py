from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.atom_selection_required_guard_v11 import (
    build_atom_selection_instruction_v11,
)
from src.combined_prompt_v11_real_runner import (
    QUESTION_ORDER,
    RESPONSE_CAP,
    execute_validation_v11,
)
from src.deepseek_internal_call_isolation_transport_mock_v2_3_4_2 import (
    CallIsolatedFrozenQuestionNativeToolMockClient,
    CallIsolatedLogicalClientV2_3_4_2,
    OfflineDeepSeekProviderV2_3_4_2,
)
from src.mock_h2_registry import FrozenH2MockRegistry
from src.online_native_tool_candidate_combined_v11 import COMBINED_PROMPT_VERSION
from src.tool_routing_prompt_v1_real_runner import (
    OFFLINE_CONFIRMATION,
    validate_offline_request,
)


class CombinedPromptV11Tests(unittest.TestCase):
    def test_selection_instruction_repeats_every_required_atom(self) -> None:
        required = [f"ATOM-{index:03d}" for index in range(1, 81)]
        catalog = SimpleNamespace(slots=[
            SimpleNamespace(slot_id="SLOT-001", required_atom_ids=["ATOM-081"]),
            SimpleNamespace(slot_id="SLOT-002", required_atom_ids=required),
            SimpleNamespace(slot_id="SLOT-003", required_atom_ids=[]),
            SimpleNamespace(slot_id="SLOT-004", required_atom_ids=[]),
            SimpleNamespace(slot_id="SLOT-005", required_atom_ids=[]),
            SimpleNamespace(slot_id="SLOT-006", required_atom_ids=["ATOM-082"]),
        ])
        instruction = build_atom_selection_instruction_v11(catalog)
        payload = instruction.split("REQUIRED_MAP=", 1)[1]
        parsed = json.loads(payload)
        self.assertEqual(parsed["SLOT-002"], required)
        self.assertIn("MUST exactly copy", instruction)
        self.assertIn("Do not abbreviate", instruction)

    def test_q04_checkpoint_passes_offline(self) -> None:
        authority = validate_offline_request(confirmation=OFFLINE_CONFIRMATION)

        def transport_factory(_question_id: str):
            logical = CallIsolatedLogicalClientV2_3_4_2(
                CallIsolatedFrozenQuestionNativeToolMockClient()
            )
            return OfflineDeepSeekProviderV2_3_4_2(logical)

        with tempfile.TemporaryDirectory() as temp:
            result = execute_validation_v11(
                api_key="offline-combined-v11-key",
                registry=FrozenH2MockRegistry(),
                transport_factory=transport_factory,
                authority=authority,
                output_parent=Path(temp),
                run_id="combined_prompt_v11_q04_offline_runner_test",
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
