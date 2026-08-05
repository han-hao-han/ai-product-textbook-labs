from __future__ import annotations

import unittest

from src.real_validation_plan_v2_1 import (
    EXPECTED_QUESTION_IDS,
    RealValidationPlanV2_1Error,
    load_real_validation_plan_v2_1,
    validate_real_validation_plan_v2_1,
)


class V2_1RealValidationPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.plan = load_real_validation_plan_v2_1()

    def test_candidate_has_no_call_authority(self) -> None:
        authorization = self.plan["authorization"]
        change = self.plan["change_control"]

        self.assertFalse(
            authorization["real_model_calls_allowed_by_this_plan"]
        )
        self.assertFalse(
            authorization["api_key_may_be_read_during_plan_design"]
        )
        self.assertFalse(
            authorization["network_may_be_opened_during_plan_design"]
        )
        self.assertFalse(change["real_call_authorized"])

    def test_same_three_questions_as_v2_baseline(self) -> None:
        selected = tuple(
            self.plan["selection_strategy"][
                "selected_question_ids_in_order"
            ]
        )
        baseline = tuple(
            self.plan["comparison_baseline"]["question_ids"]
        )

        self.assertEqual(selected, EXPECTED_QUESTION_IDS)
        self.assertEqual(baseline, EXPECTED_QUESTION_IDS)
        self.assertEqual(
            self.plan["comparison_baseline"]["run_id"],
            "agent_v2_online_20260731T144944_474379+0800",
        )

    def test_six_attempt_zero_retry_progressive_gate(self) -> None:
        limits = self.plan["hard_limits"]
        cases = self.plan["case_gates"]

        self.assertEqual(
            sum(case["expected_request_attempts"] for case in cases),
            6,
        )
        self.assertEqual(limits["request_attempt_upper_bound"], 6)
        self.assertEqual(limits["automatic_retry_count"], 0)
        self.assertFalse(limits["parallel_requests"])
        self.assertTrue(limits["stop_on_first_case_failure"])
        self.assertEqual(
            limits["expected_endpoint_counts_if_all_pass"],
            {
                "standard_json": 4,
                "beta_strict_tool": 2,
                "total": 6,
            },
        )
        self.assertTrue(
            self.plan["pause"][
                "old_request_attempt_upper_bound_must_not_be_reused_without_recalculation"
            ]
        )

    def test_paused_plan_cannot_pass_execution_preflight(self) -> None:
        self.assertEqual(
            self.plan["status"],
            "paused_after_mainline_boundaries_reopened",
        )
        with self.assertRaises(RealValidationPlanV2_1Error):
            validate_real_validation_plan_v2_1()

    def test_preflight_evidence_does_not_claim_real_execution(
        self,
    ) -> None:
        preflight = self.plan["offline_preflight"]

        self.assertEqual(preflight["status"], "passed")
        self.assertFalse(preflight["real_network_opened"])
        self.assertFalse(preflight["api_key_read"])
        self.assertFalse(preflight["real_model_called"])
        self.assertEqual(
            preflight["request_attempt_upper_bound"],
            6,
        )

    def test_pause_does_not_authorize_calls_or_retries(self) -> None:
        self.assertFalse(
            self.plan["pause"]["real_model_calls_allowed"]
        )
        self.assertFalse(
            self.plan["authorization"][
                "real_model_calls_allowed_by_this_plan"
            ]
        )
        self.assertEqual(
            self.plan["hard_limits"]["automatic_retry_count"],
            0,
        )


if __name__ == "__main__":
    unittest.main()
