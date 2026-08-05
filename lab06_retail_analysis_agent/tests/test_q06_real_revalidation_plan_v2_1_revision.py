from __future__ import annotations

import unittest
from copy import deepcopy
from typing import Any

from src.deepseek_client import ChatCompletionResult, ProviderToolCall
from src.deepseek_provider_schema_adapter_v2_1_revision import (
    DEEPSEEK_NONE_SENTINEL,
)
from src.fixed_question_validation import (
    load_frozen_questions,
    validate_fixed_question,
)
from src.mock_h2_registry import FrozenH2MockRegistry
from src.native_tool_transport_mock_v2_1_revision import (
    OfflineNativeToolTransportV2_1Revision,
)
from src.online_native_tool_candidate_v2_1_revision import (
    NativeToolOnlineCandidateV2_1Revision,
)
from src.q06_provider_schema_revalidation_mock import (
    Q06ProviderSchemaRevalidationMockClient,
)
from src.q06_real_revalidation_plan_v2_1_revision import (
    Q06RealRevalidationPlanError,
    load_q06_real_revalidation_plan,
    validate_q06_real_revalidation_plan,
)


class InvalidFirstQ06ResponseClient:
    def complete_strict_tools(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: str = "auto",
    ) -> ChatCompletionResult:
        return ChatCompletionResult(
            finish_reason="tool_calls",
            content=None,
            tool_calls=(
                ProviderToolCall(
                    provider_call_id="invalid-q06-first",
                    tool_name="analyze_time_trend",
                    arguments={
                        "period": "complete_months_only",
                        "start_date": DEEPSEEK_NONE_SENTINEL,
                        "end_date": DEEPSEEK_NONE_SENTINEL,
                        "grain": "monthly",
                        "metric": "sales_amount",
                        "exclude_incomplete_periods": True,
                    },
                ),
            ),
            raw_response={"offline_invalid_q06": True},
            usage=None,
        )


class Q06RealRevalidationPlanV2_1RevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.plan = load_q06_real_revalidation_plan()

    def test_consumed_real_run_is_valid_but_grants_no_further_authority(self) -> None:
        result = validate_q06_real_revalidation_plan()
        self.assertEqual(result.status, "passed")
        self.assertEqual(result.question_ids, ("Q06",))
        self.assertEqual(result.model, "deepseek-v4-pro")
        self.assertEqual(result.response_attempt_upper_bound, 3)
        self.assertEqual(result.expected_beta_requests, 3)
        self.assertEqual(result.automatic_retry_count, 0)
        self.assertFalse(result.real_model_calls_allowed)
        self.assertEqual(
            self.plan["compatible_authorization"]["status"],
            "consumed_by_failed_run",
        )
        self.assertEqual(
            self.plan["real_validation"]["third_observed_tool"],
            "get_data_profile",
        )

    def test_prior_authorization_cannot_be_reused(self) -> None:
        authorization = self.plan["authorization"]
        self.assertFalse(authorization["prior_five_response_authorization_reusable"])
        self.assertTrue(authorization["separate_user_freeze_required"])
        self.assertTrue(
            authorization["separate_user_call_authorization_required"]
        )
        self.assertEqual(
            authorization["runner_confirmation_constant"],
            "I_AUTHORIZE_Q06_PROVIDER_SCHEMA_REVALIDATION",
        )

    def test_user_freeze_matches_exact_plan_and_grants_no_authority(self) -> None:
        self.assertEqual(
            self.plan["status"],
            "frozen_real_revalidation_failed_after_three_responses_extra_tool_call_pending_user_decision",
        )
        freeze = self.plan["user_freeze"]
        self.assertEqual(freeze["question_ids"], ["Q06"])
        self.assertEqual(freeze["model"], "deepseek-v4-pro")
        self.assertEqual(freeze["response_attempt_upper_bound"], 3)
        self.assertEqual(freeze["automatic_retry_count"], 0)
        self.assertTrue(freeze["freeze_does_not_authorize_real_calls"])
        self.assertFalse(
            self.plan["authorization"]["real_model_calls_allowed_by_this_plan"]
        )

    def test_scope_cap_retry_and_authority_cannot_be_broadened(self) -> None:
        q08 = deepcopy(self.plan)
        q08["case_gate"]["question_ids"] = ["Q06", "Q08"]
        with self.assertRaises(Q06RealRevalidationPlanError):
            validate_q06_real_revalidation_plan(q08)

        cap = deepcopy(self.plan)
        cap["hard_limits"]["response_attempt_upper_bound"] = 4
        with self.assertRaises(Q06RealRevalidationPlanError):
            validate_q06_real_revalidation_plan(cap)

        retry = deepcopy(self.plan)
        retry["hard_limits"]["automatic_retry_count"] = 1
        with self.assertRaises(Q06RealRevalidationPlanError):
            validate_q06_real_revalidation_plan(retry)

        authority = deepcopy(self.plan)
        authority["authorization"]["real_model_calls_allowed_by_this_plan"] = True
        with self.assertRaises(Q06RealRevalidationPlanError):
            validate_q06_real_revalidation_plan(authority)

    def test_injected_transport_completes_exact_three_response_q06(self) -> None:
        transport = OfflineNativeToolTransportV2_1Revision(
            Q06ProviderSchemaRevalidationMockClient()
        )
        candidate = NativeToolOnlineCandidateV2_1Revision(
            api_key="offline-q06-plan-test",
            registry=FrozenH2MockRegistry(),
            response_limit=3,
            transport=transport,
            question_count=1,
        )
        outcome = candidate.run_turn(
            session_id="SESSION-q06-plan-test",
            turn_id="TURN-006",
            question=load_frozen_questions()["Q06"]["question"],
        )

        self.assertEqual(
            validate_fixed_question("Q06", outcome).status,
            "protocol_and_dataflow_passed",
        )
        self.assertEqual(outcome.status, "completed")
        self.assertEqual(len(transport.requests), 3)
        self.assertEqual(candidate.response_limit_snapshot().attempted, 3)
        self.assertEqual(
            candidate.last_trace[0].selected_arguments["start_date"],
            DEEPSEEK_NONE_SENTINEL,
        )
        self.assertIsNone(
            candidate.last_trace[0].normalized_arguments["start_date"]
        )
        self.assertEqual(
            [call.tool_name for call in outcome.tool_calls],
            ["analyze_time_trend", "rank_products"],
        )

    def test_invalid_first_response_stops_after_one_attempt(self) -> None:
        transport = OfflineNativeToolTransportV2_1Revision(
            InvalidFirstQ06ResponseClient()
        )
        candidate = NativeToolOnlineCandidateV2_1Revision(
            api_key="offline-q06-failure-test",
            registry=FrozenH2MockRegistry(),
            response_limit=3,
            transport=transport,
            question_count=1,
        )
        outcome = candidate.run_turn(
            session_id="SESSION-q06-failure-test",
            turn_id="TURN-006",
            question=load_frozen_questions()["Q06"]["question"],
        )

        self.assertEqual(outcome.status, "failed")
        self.assertEqual(outcome.error_stage, "model_response")
        self.assertEqual(len(transport.requests), 1)
        self.assertEqual(candidate.response_limit_snapshot().attempted, 1)
        self.assertEqual(outcome.tool_calls, ())


if __name__ == "__main__":
    unittest.main()
