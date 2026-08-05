from __future__ import annotations

import unittest
from copy import deepcopy

from src.q06_v2_2_1_flash_real_revalidation_plan import (
    Q06V2_2_1FlashRealPlanError,
    load_q06_v2_2_1_flash_real_plan,
    validate_q06_v2_2_1_flash_real_plan,
)


class Q06V2_2_1FlashRealRevalidationPlanTests(unittest.TestCase):
    def test_design_is_q06_flash_only_and_not_authorized(self) -> None:
        preflight = validate_q06_v2_2_1_flash_real_plan()
        self.assertEqual(preflight.model, "deepseek-v4-flash")
        self.assertEqual(preflight.question_ids, ("Q06",))
        self.assertEqual(preflight.response_attempt_upper_bound, 3)
        self.assertEqual(preflight.automatic_retry_count, 0)
        self.assertEqual(
            preflight.tool_choice_sequence,
            ("auto", "auto", "none"),
        )
        self.assertEqual(
            preflight.response_format_sequence,
            (None, None, {"type": "json_object"}),
        )
        self.assertFalse(preflight.real_model_calls_allowed)
        self.assertTrue(preflight.guarded_runner_ready)
        plan = load_q06_v2_2_1_flash_real_plan()
        self.assertEqual(
            plan["status"],
            "frozen_real_validation_failed_pending_user_decision",
        )
        self.assertTrue(
            plan["user_freeze"]["freeze_does_not_authorize_real_calls"]
        )

    def test_json_mode_on_business_tool_response_is_rejected(self) -> None:
        changed = deepcopy(load_q06_v2_2_1_flash_real_plan())
        changed["request_protocol"]["response_format_sequence"][1] = {
            "type": "json_object"
        }
        with self.assertRaises(Q06V2_2_1FlashRealPlanError):
            validate_q06_v2_2_1_flash_real_plan(changed)

    def test_retry_or_broader_question_scope_is_rejected(self) -> None:
        retries = deepcopy(load_q06_v2_2_1_flash_real_plan())
        retries["hard_limits"]["automatic_retry_count"] = 1
        with self.assertRaises(Q06V2_2_1FlashRealPlanError):
            validate_q06_v2_2_1_flash_real_plan(retries)

        broader = deepcopy(load_q06_v2_2_1_flash_real_plan())
        broader["scope"]["question_ids"] = ["Q06", "Q09"]
        with self.assertRaises(Q06V2_2_1FlashRealPlanError):
            validate_q06_v2_2_1_flash_real_plan(broader)

    def test_design_cannot_claim_real_authority_or_ready_runner(self) -> None:
        authorized = deepcopy(load_q06_v2_2_1_flash_real_plan())
        authorized["authorization"]["status"] = "authorized_by_user"
        authorized["authorization"]["real_model_calls_allowed"] = True
        with self.assertRaises(Q06V2_2_1FlashRealPlanError):
            validate_q06_v2_2_1_flash_real_plan(authorized)

        runnable = deepcopy(load_q06_v2_2_1_flash_real_plan())
        runnable["implementation"]["guarded_runner"] = "scripts/run.py"
        runnable["implementation"]["guarded_runner_status"] = "ready"
        with self.assertRaises(Q06V2_2_1FlashRealPlanError):
            validate_q06_v2_2_1_flash_real_plan(runnable)

    def test_dsml_repair_or_weakened_acceptance_is_rejected(self) -> None:
        repair = deepcopy(load_q06_v2_2_1_flash_real_plan())
        repair["response_gates"][2][
            "dsml_or_markdown_repair_allowed"
        ] = True
        with self.assertRaises(Q06V2_2_1FlashRealPlanError):
            validate_q06_v2_2_1_flash_real_plan(repair)

        acceptance = deepcopy(load_q06_v2_2_1_flash_real_plan())
        acceptance["program_acceptance"][
            "manual_review_required"
        ] = False
        with self.assertRaises(Q06V2_2_1FlashRealPlanError):
            validate_q06_v2_2_1_flash_real_plan(acceptance)


if __name__ == "__main__":
    unittest.main()
