from __future__ import annotations

import unittest
from copy import deepcopy

from src.fixed_question_validation import (
    load_frozen_questions,
    validate_fixed_question,
)
from src.mock_h2_registry import FrozenH2MockRegistry
from src.mock_native_tool_client_v2_1_revision import (
    FrozenQuestionNativeToolMockClient,
)
from src.native_tool_real_validation_plan_v2_1_revision import (
    EXPECTED_QUESTION_IDS,
    NativeToolRealValidationPlanError,
    load_native_tool_real_validation_plan,
    validate_native_tool_real_validation_plan,
)
from src.native_tool_transport_mock_v2_1_revision import (
    OfflineNativeToolTransportV2_1Revision,
)
from src.online_native_tool_candidate_v2_1_revision import (
    NativeToolOnlineCandidateV2_1Revision,
)


class NativeToolRealValidationPlanV2_1RevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.plan = load_native_tool_real_validation_plan()

    def test_candidate_plan_passes_and_has_no_call_authority(self) -> None:
        result = validate_native_tool_real_validation_plan()

        self.assertEqual(result.status, "passed")
        self.assertEqual(result.question_ids, EXPECTED_QUESTION_IDS)
        self.assertEqual(result.response_attempt_upper_bound, 5)
        self.assertEqual(result.expected_beta_requests, 5)
        self.assertEqual(result.expected_standard_json_requests, 0)
        self.assertFalse(result.real_model_calls_allowed)
        self.assertFalse(
            self.plan["authorization"][
                "real_model_calls_allowed_by_this_plan"
            ]
        )
        self.assertTrue(self.plan["change_control"]["runner_implemented"])

    def test_response_count_is_native_three_plus_one_plus_one(self) -> None:
        cases = self.plan["case_gates"]
        self.assertEqual(
            [case["expected_response_attempts"] for case in cases],
            [3, 1, 1],
        )
        self.assertEqual(
            sum(case["expected_response_attempts"] for case in cases),
            5,
        )
        self.assertEqual(
            self.plan["hard_limits"]["expected_endpoint_counts_if_all_pass"],
            {"beta_strict_tool": 5, "standard_json": 0, "total": 5},
        )

    def test_five_response_plan_is_frozen_but_ten_response_authorization_is_not_accepted(
        self,
    ) -> None:
        self.assertEqual(
            self.plan["status"],
            "frozen_real_validation_failed_after_one_response_pending_user_decision",
        )
        self.assertTrue(
            self.plan["change_control"][
                "response_attempt_upper_bound_frozen_before_call"
            ]
        )
        review = self.plan["prior_incompatible_authorization_review"]
        self.assertEqual(review["received_response_attempt_upper_bound"], 10)
        self.assertEqual(review["frozen_response_attempt_upper_bound"], 5)
        self.assertFalse(review["real_call_authorized"])
        self.assertEqual(
            review["status"],
            "not_accepted_upper_bound_conflicts_with_frozen_plan",
        )
        compatible = self.plan["compatible_authorization"]
        self.assertEqual(compatible["response_attempt_upper_bound"], 5)
        self.assertEqual(compatible["status"], "consumed_by_failed_run")
        self.assertTrue(compatible["authorization_matches_frozen_plan"])

    def test_recipe_or_standard_json_gate_cannot_return(self) -> None:
        recipe = deepcopy(self.plan)
        recipe["model_protocol"]["recipe_router_allowed"] = True
        with self.assertRaises(NativeToolRealValidationPlanError):
            validate_native_tool_real_validation_plan(recipe)

        json_gate = deepcopy(self.plan)
        json_gate["model_protocol"]["standard_json_gate_allowed"] = True
        with self.assertRaises(NativeToolRealValidationPlanError):
            validate_native_tool_real_validation_plan(json_gate)

    def test_cap_retry_and_manual_review_cannot_be_weakened(self) -> None:
        too_many = deepcopy(self.plan)
        too_many["hard_limits"]["response_attempt_upper_bound"] = 6
        with self.assertRaises(NativeToolRealValidationPlanError):
            validate_native_tool_real_validation_plan(too_many)

        retry = deepcopy(self.plan)
        retry["hard_limits"]["automatic_retry_count"] = 1
        with self.assertRaises(NativeToolRealValidationPlanError):
            validate_native_tool_real_validation_plan(retry)

        no_manual = deepcopy(self.plan)
        no_manual["stage_acceptance"]["manual_review_required"] = False
        with self.assertRaises(NativeToolRealValidationPlanError):
            validate_native_tool_real_validation_plan(no_manual)

    def test_selected_cases_use_exact_frozen_semantics(self) -> None:
        cases = {case["question_id"]: case for case in self.plan["case_gates"]}
        self.assertEqual(tuple(cases), EXPECTED_QUESTION_IDS)
        self.assertEqual(
            cases["Q06"]["expected_tool_sequence"],
            ["analyze_time_trend", "rank_products"],
        )
        self.assertEqual(
            cases["Q08"]["required_clarification_topics"],
            [
                "time_range",
                "metric",
                "comparison_dimension_or_objects",
            ],
        )
        self.assertEqual(
            cases["Q09"]["required_missing_fields"],
            ["cost", "profit"],
        )

    def test_injected_transport_preflight_consumes_exactly_five(self) -> None:
        transport = OfflineNativeToolTransportV2_1Revision(
            FrozenQuestionNativeToolMockClient()
        )
        candidate = NativeToolOnlineCandidateV2_1Revision(
            api_key="offline-plan-test",
            registry=FrozenH2MockRegistry(),
            response_limit=5,
            transport=transport,
            question_count=3,
        )
        questions = load_frozen_questions()
        for index, question_id in enumerate(EXPECTED_QUESTION_IDS, start=1):
            outcome = candidate.run_turn(
                session_id="SESSION-native-real-plan-test",
                turn_id=f"TURN-{index:03d}",
                question=questions[question_id]["question"],
            )
            expected_status = (
                "protocol_and_dataflow_passed"
                if question_id == "Q06"
                else "passed_deterministic_pending_manual_review"
            )
            self.assertEqual(
                validate_fixed_question(question_id, outcome).status,
                expected_status,
            )

        self.assertEqual(len(transport.requests), 5)
        self.assertEqual(candidate.response_limit_snapshot().attempted, 5)
        self.assertTrue(all(request.tool_count == 7 for request in transport.requests))


if __name__ == "__main__":
    unittest.main()
