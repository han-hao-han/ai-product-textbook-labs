from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.deepseek_frozen_six_slot_transport_mock_v2_3_4 import (
    FrozenSixSlotLogicalClientV2_3_4,
    OfflineDeepSeekProviderV2_3_4,
)
from src.mock_h2_registry import FrozenH2MockRegistry
from src.mock_native_tool_client_v2_1_revision import FrozenQuestionNativeToolMockClient
from src.q02_frozen_six_slot_v2_3_4_runner import (
    OFFLINE_CONFIRMATION, REAL_CONFIRMATION, Q02FrozenSlotRunnerError,
    execute_q02, validate_offline_execution_request, validate_real_execution_request,
)


def _provider(mutator=None):
    return OfflineDeepSeekProviderV2_3_4(
        FrozenSixSlotLogicalClientV2_3_4(
            FrozenQuestionNativeToolMockClient(), selection_mutator=mutator
        )
    )


class Q02FrozenSixSlotRunnerTests(unittest.TestCase):
    def test_offline_success_saves_three_responses(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = execute_q02(
                api_key="offline-v234-secret", registry=FrozenH2MockRegistry(),
                transport=_provider(),
                authority=validate_offline_execution_request(confirmation=OFFLINE_CONFIRMATION),
                output_parent=Path(temporary), run_id="offline-v234-success",
            )
            parsed = list((result.output_dir / "responses" / "parsed").glob("*.json"))
            state = (result.output_dir / "run_state.json").read_text(encoding="utf-8")
        self.assertTrue(result.passed, result.summary)
        self.assertEqual(result.summary["actual_response_attempts"], 3)
        self.assertEqual(len(parsed), 3)
        self.assertTrue(result.summary["final_report_request_sent"])
        self.assertNotIn("offline-v234-secret", state)

    def test_invalid_selection_stops_after_two_saved_responses(self) -> None:
        def invalidate(payload):
            payload["selections"][1]["atom_ids"].append("ATOM-999")
            return payload

        with tempfile.TemporaryDirectory() as temporary:
            result = execute_q02(
                api_key="offline-v234-invalid-secret", registry=FrozenH2MockRegistry(),
                transport=_provider(invalidate),
                authority=validate_offline_execution_request(confirmation=OFFLINE_CONFIRMATION),
                output_parent=Path(temporary), run_id="offline-v234-invalid",
            )
            parsed = list((result.output_dir / "responses" / "parsed").glob("*.json"))
        self.assertFalse(result.passed)
        self.assertEqual(result.summary["root_failure_stage"], "atom_selection_validation")
        self.assertEqual(result.summary["actual_response_attempts"], 2)
        self.assertEqual(len(parsed), 2)
        self.assertFalse(result.summary["final_report_request_sent"])

    def test_real_entry_rejects_non_exact_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(Q02FrozenSlotRunnerError, "exact real confirmation"):
                validate_real_execution_request(
                    question_id="Q02", model="deepseek-v4-flash",
                    approved_model_responses=3, automatic_retries=0,
                    confirmation=REAL_CONFIRMATION + "-WRONG", consumption_root=Path(temporary),
                )


if __name__ == "__main__":
    unittest.main()
