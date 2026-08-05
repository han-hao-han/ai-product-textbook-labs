from __future__ import annotations

import unittest
from copy import deepcopy

from src.q01_q10_new_harness_flash_real_validation_plan import (
    Q01Q10NewHarnessFlashPlanError,
    load_q01_q10_new_harness_flash_plan,
    validate_q01_q10_new_harness_flash_plan,
)


class Q01Q10NewHarnessFlashPlanTests(unittest.TestCase):
    def test_two_batch_plan_is_offline_and_not_authorized(self) -> None:
        result = validate_q01_q10_new_harness_flash_plan()
        self.assertEqual(result.model, "deepseek-v4-flash")
        self.assertEqual(result.batch_a_attempt_cap, 8)
        self.assertEqual(result.batch_b_attempt_cap, 12)
        self.assertEqual(result.total_attempt_cap, 20)
        self.assertEqual(result.automatic_retry_count, 0)
        self.assertFalse(result.real_model_calls_allowed)
        self.assertTrue(result.guarded_runner_ready)
        plan = load_q01_q10_new_harness_flash_plan()
        self.assertEqual(
            plan["status"],
            "frozen_by_user_pending_guarded_runner_design_and_separate_batch_authorization",
        )
        self.assertEqual(plan["user_freeze"]["status"], "frozen_by_user")
        self.assertTrue(
            plan["user_freeze"]["freeze_does_not_authorize_real_calls"]
        )
        self.assertTrue(
            plan["user_freeze"][
                "freeze_does_not_authorize_runner_implementation"
            ]
        )

    def test_batch_partition_covers_every_question_exactly_once(self) -> None:
        result = validate_q01_q10_new_harness_flash_plan()
        combined = result.batch_a_question_ids + result.batch_b_question_ids
        self.assertEqual(len(combined), 10)
        self.assertEqual(set(combined), {f"Q{index:02d}" for index in range(1, 11)})

    def test_attempt_cap_or_retry_drift_is_rejected(self) -> None:
        changed = deepcopy(load_q01_q10_new_harness_flash_plan())
        changed["batches"][0]["maximum_response_attempts"] = 9
        with self.assertRaises(Q01Q10NewHarnessFlashPlanError):
            validate_q01_q10_new_harness_flash_plan(changed)

        changed = deepcopy(load_q01_q10_new_harness_flash_plan())
        changed["failure_and_stop_rules"]["automatic_retry_count"] = 1
        with self.assertRaises(Q01Q10NewHarnessFlashPlanError):
            validate_q01_q10_new_harness_flash_plan(changed)

    def test_network_failure_cannot_continue_or_auto_resume(self) -> None:
        changed = deepcopy(load_q01_q10_new_harness_flash_plan())
        changed["failure_and_stop_rules"]["stop_current_batch_on_first_transport_failure"] = False
        with self.assertRaises(Q01Q10NewHarnessFlashPlanError):
            validate_q01_q10_new_harness_flash_plan(changed)

        changed = deepcopy(load_q01_q10_new_harness_flash_plan())
        changed["failure_and_stop_rules"]["automatic_resume_after_network_recovery"] = True
        with self.assertRaises(Q01Q10NewHarnessFlashPlanError):
            validate_q01_q10_new_harness_flash_plan(changed)

    def test_protocol_only_or_automatic_manual_pass_is_rejected(self) -> None:
        changed = deepcopy(load_q01_q10_new_harness_flash_plan())
        changed["deterministic_acceptance"]["protocol_and_dataflow_passed_is_real_success"] = True
        with self.assertRaises(Q01Q10NewHarnessFlashPlanError):
            validate_q01_q10_new_harness_flash_plan(changed)

        changed = deepcopy(load_q01_q10_new_harness_flash_plan())
        changed["manual_review"]["fully_accepted_label_may_be_set_automatically"] = True
        with self.assertRaises(Q01Q10NewHarnessFlashPlanError):
            validate_q01_q10_new_harness_flash_plan(changed)

    def test_freeze_cannot_authorize_calls_or_batch_b(self) -> None:
        changed = deepcopy(load_q01_q10_new_harness_flash_plan())
        changed["authorization"]["real_model_calls_allowed"] = True
        with self.assertRaises(Q01Q10NewHarnessFlashPlanError):
            validate_q01_q10_new_harness_flash_plan(changed)

        changed = deepcopy(load_q01_q10_new_harness_flash_plan())
        changed["authorization"]["batch_a_authorization_does_not_authorize_batch_b"] = False
        with self.assertRaises(Q01Q10NewHarnessFlashPlanError):
            validate_q01_q10_new_harness_flash_plan(changed)

    def test_frozen_sources_and_v2_2_3_cannot_drift(self) -> None:
        changed = deepcopy(load_q01_q10_new_harness_flash_plan())
        changed["scope"]["h2_reference_answers_changed"] = True
        with self.assertRaises(Q01Q10NewHarnessFlashPlanError):
            validate_q01_q10_new_harness_flash_plan(changed)

    def test_frozen_record_cannot_change_caps_or_grant_authority(self) -> None:
        changed = deepcopy(load_q01_q10_new_harness_flash_plan())
        changed["user_freeze"]["batch_a_response_attempt_upper_bound"] = 9
        with self.assertRaises(Q01Q10NewHarnessFlashPlanError):
            validate_q01_q10_new_harness_flash_plan(changed)

        changed = deepcopy(load_q01_q10_new_harness_flash_plan())
        changed["user_freeze"]["freeze_does_not_authorize_real_calls"] = False
        with self.assertRaises(Q01Q10NewHarnessFlashPlanError):
            validate_q01_q10_new_harness_flash_plan(changed)

        changed = deepcopy(load_q01_q10_new_harness_flash_plan())
        changed["scope"]["v2_2_3_resumed"] = True
        with self.assertRaises(Q01Q10NewHarnessFlashPlanError):
            validate_q01_q10_new_harness_flash_plan(changed)


if __name__ == "__main__":
    unittest.main()
