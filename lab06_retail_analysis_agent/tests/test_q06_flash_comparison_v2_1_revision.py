from __future__ import annotations

import tempfile
import unittest
from argparse import Namespace
from copy import deepcopy
from pathlib import Path

from scripts import run_q06_flash_comparison_v2_1_revision as flash_runner
from scripts import run_q06_real_revalidation_v2_1_revision as q06_runner
from src.mock_h2_registry import FrozenH2MockRegistry
from src.native_tool_transport_mock_v2_1_revision import (
    OfflineNativeToolTransportV2_1Revision,
)
from src.q06_flash_comparison_plan_v2_1_revision import (
    Q06FlashComparisonPlanError,
    load_q06_flash_comparison_plan,
    validate_q06_flash_comparison_plan,
)
from src.q06_provider_schema_revalidation_mock import (
    Q06ProviderSchemaRevalidationMockClient,
)


def exact_args() -> Namespace:
    return Namespace(
        question_id="Q06",
        approved_model_responses=3,
        automatic_retries=0,
        confirm_real_model_calls=flash_runner.FLASH_CONFIRMATION,
    )


def offline_validated_plan() -> dict:
    plan = deepcopy(load_q06_flash_comparison_plan())
    plan["status"] = (
        "frozen_authorized_guarded_runner_offline_validated_pending_execution"
    )
    plan["implementation"]["guarded_runner_status"] = (
        "implemented_and_offline_validated"
    )
    plan["authorization"]["status"] = "authorized_by_user"
    return plan


class Q06FlashComparisonV2_1RevisionTests(unittest.TestCase):
    def test_plan_keeps_same_q06_inputs_and_zero_pro_calls(self) -> None:
        preflight = validate_q06_flash_comparison_plan()
        plan = load_q06_flash_comparison_plan()
        self.assertEqual(preflight.model, "deepseek-v4-flash")
        self.assertEqual(preflight.response_attempt_upper_bound, 3)
        self.assertEqual(preflight.automatic_retry_count, 0)
        self.assertFalse(preflight.real_model_calls_allowed)
        self.assertFalse(plan["comparison_scope"]["baseline_repeated"])
        self.assertEqual(plan["hard_limits"]["pro_response_attempts_allowed"], 0)
        self.assertEqual(
            plan["authorization"]["status"], "consumed_by_failed_run"
        )
        self.assertEqual(plan["real_run"]["actual_pro_response_attempts"], 0)

    def test_consumed_authorization_cannot_be_reused(self) -> None:
        with self.assertRaisesRegex(ValueError, "not authorized"):
            flash_runner.validate_execution_request(exact_args())

    def test_scope_or_model_drift_is_rejected(self) -> None:
        changed_prompt = deepcopy(load_q06_flash_comparison_plan())
        changed_prompt["comparison_scope"]["prompt_changed"] = True
        with self.assertRaises(Q06FlashComparisonPlanError):
            validate_q06_flash_comparison_plan(changed_prompt)

        changed_model = deepcopy(load_q06_flash_comparison_plan())
        changed_model["model_protocol"]["requested_model"] = "deepseek-v4-pro"
        with self.assertRaises(Q06FlashComparisonPlanError):
            validate_q06_flash_comparison_plan(changed_model)

    def test_exact_offline_validated_authorization_passes_runner_gate(self) -> None:
        authority = flash_runner.validate_execution_request(
            exact_args(), plan=offline_validated_plan()
        )
        self.assertEqual(authority.model, "deepseek-v4-flash")

    def test_flash_offline_transport_uses_only_flash_and_three_responses(self) -> None:
        transport = OfflineNativeToolTransportV2_1Revision(
            Q06ProviderSchemaRevalidationMockClient(),
            expected_model="deepseek-v4-flash",
        )
        with tempfile.TemporaryDirectory(
            dir=flash_runner.PROJECT_ROOT / "results" / "raw"
        ) as temporary:
            result = q06_runner.execute_q06_validation(
                api_key="offline-flash-key",
                registry=FrozenH2MockRegistry(),
                transport=transport,
                output_parent=Path(temporary),
                run_id="offline-flash",
                model="deepseek-v4-flash",
            )
            self.assertFalse(result.passed)
            self.assertIn(
                "fixed_question_validation_failed",
                result.case_payload["program_failures"],
            )
            self.assertEqual(
                result.case_payload["fixed_question_validation"]["status"],
                "protocol_and_dataflow_passed",
            )
            self.assertEqual(result.summary["model_authorized"], "deepseek-v4-flash")
            self.assertEqual(result.summary["actual_model_response_attempts"], 3)
            self.assertEqual(len(transport.requests), 3)
            self.assertTrue(
                all(request.model == "deepseek-v4-flash" for request in transport.requests)
            )


if __name__ == "__main__":
    unittest.main()
