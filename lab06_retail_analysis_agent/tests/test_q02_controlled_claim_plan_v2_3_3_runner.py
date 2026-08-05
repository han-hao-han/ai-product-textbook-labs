from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.deepseek_controlled_claim_plan_transport_mock_v2_3_3 import (
    ControlledClaimPlanLogicalClientV2_3_3,
    OfflineDeepSeekProviderV2_3_3,
)
from src.mock_h2_registry import FrozenH2MockRegistry
from src.mock_native_tool_client_v2_1_revision import FrozenQuestionNativeToolMockClient
from src.q02_controlled_claim_plan_v2_3_3_runner import (
    OFFLINE_CONFIRMATION,
    REAL_CONFIRMATION,
    Q02ControlledClaimPlanRunnerError,
    execute_q02,
    validate_offline_execution_request,
    validate_real_execution_request,
)


def _provider(mutator=None):
    return OfflineDeepSeekProviderV2_3_3(
        ControlledClaimPlanLogicalClientV2_3_3(
            FrozenQuestionNativeToolMockClient(), plan_mutator=mutator
        )
    )


class Q02ControlledClaimPlanRunnerTests(unittest.TestCase):
    def test_offline_success_saves_three_responses(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = execute_q02(
                api_key="offline-v233-q02-secret",
                registry=FrozenH2MockRegistry(), transport=_provider(),
                authority=validate_offline_execution_request(confirmation=OFFLINE_CONFIRMATION),
                output_parent=Path(temporary), run_id="offline-v233-q02-success",
            )
            state = (result.output_dir / "run_state.json").read_text(encoding="utf-8")
        self.assertTrue(result.passed, result.summary)
        self.assertEqual(result.summary["actual_response_attempts"], 3)
        self.assertTrue(result.summary["final_report_request_sent"])
        self.assertNotIn("offline-v233-q02-secret", state)

    def test_invalid_plan_stops_after_two_saved_responses(self) -> None:
        def invalidate(payload):
            target = next(item for item in payload["slots"] if item["claim_mode"] == "ranked_observation")
            target["requested_superlative_metric"] = "sales_quantity"
            return payload

        with tempfile.TemporaryDirectory() as temporary:
            result = execute_q02(
                api_key="offline-v233-invalid-secret",
                registry=FrozenH2MockRegistry(), transport=_provider(invalidate),
                authority=validate_offline_execution_request(confirmation=OFFLINE_CONFIRMATION),
                output_parent=Path(temporary), run_id="offline-v233-q02-invalid",
            )
            parsed = list((result.output_dir / "responses" / "parsed").glob("*.json"))
        self.assertFalse(result.passed)
        self.assertEqual(result.summary["root_failure_stage"], "claim_plan_validation")
        self.assertEqual(result.summary["actual_response_attempts"], 2)
        self.assertFalse(result.summary["final_report_request_sent"])
        self.assertEqual(len(parsed), 2)

    def test_real_entry_is_default_denied(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(Q02ControlledClaimPlanRunnerError, "no exact unconsumed"):
                validate_real_execution_request(
                    question_id="Q02", model="deepseek-v4-flash",
                    approved_model_responses=3, automatic_retries=0,
                    confirmation=REAL_CONFIRMATION,
                    consumption_root=Path(temporary),
                )


if __name__ == "__main__":
    unittest.main()
