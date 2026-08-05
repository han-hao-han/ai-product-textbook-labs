from __future__ import annotations

import unittest

from src.deepseek_controlled_claim_plan_transport_mock_v2_3_3 import (
    ControlledClaimPlanLogicalClientV2_3_3,
    OfflineDeepSeekProviderV2_3_3,
)
from src.fixed_question_validation import load_frozen_questions, validate_fixed_question
from src.mock_h2_registry import FrozenH2MockRegistry
from src.mock_native_tool_client_v2_1_revision import FrozenQuestionNativeToolMockClient
from src.online_native_tool_candidate_v2_3_3 import NativeToolOnlineCandidateV2_3_3


EXPECTED_RESPONSES = {
    "Q01": 3, "Q02": 3, "Q03": 3, "Q04": 3, "Q05": 4,
    "Q06": 4, "Q07": 4, "Q08": 1, "Q09": 1, "Q10": 1,
}


def _candidate(question_id: str, *, plan_mutator=None):
    logical = ControlledClaimPlanLogicalClientV2_3_3(
        FrozenQuestionNativeToolMockClient(),
        plan_mutator=plan_mutator,
    )
    provider = OfflineDeepSeekProviderV2_3_3(logical)
    candidate = NativeToolOnlineCandidateV2_3_3(
        api_key="offline-v233-integrated-key",
        registry=FrozenH2MockRegistry(),
        response_limit=EXPECTED_RESPONSES[question_id],
        transport=provider,
    )
    return candidate, provider


class OnlineNativeToolCandidateV2_3_3Tests(unittest.TestCase):
    def test_q01_q10_integrated_mock_end_to_end(self) -> None:
        questions = load_frozen_questions()
        for question_id, expected in EXPECTED_RESPONSES.items():
            with self.subTest(question_id=question_id):
                candidate, provider = _candidate(question_id)
                outcome = candidate.run_turn(
                    session_id=f"SESSION-v233-integrated-{question_id.lower()}",
                    turn_id=f"TURN-{int(question_id[1:]):03d}",
                    question=questions[question_id]["question"],
                    result_root="results/raw/v2_3_3_integrated_test",
                )
                fixed = validate_fixed_question(question_id, outcome)
                self.assertEqual(fixed.status, "passed_deterministic_pending_manual_review", fixed.issues)
                snapshot = candidate.response_limit_snapshot()
                self.assertEqual(snapshot.attempted, expected)
                self.assertEqual(snapshot.completed, expected)
                self.assertEqual(snapshot.failed, 0)
                self.assertEqual(len(provider.requests), expected)
                if question_id <= "Q07":
                    self.assertEqual(len(candidate.claim_plan_trace), 1)
                    self.assertEqual(candidate.claim_plan_trace[0].status, "passed")
                    self.assertEqual(
                        candidate.transport_audit_payload()["request_phases"][-2:],
                        ["controlled_claim_plan_generation", "final_report_from_validated_claim_plan"],
                    )
                else:
                    self.assertEqual(candidate.claim_plan_trace, ())

    def test_invalid_q02_plan_stops_before_final_report_response(self) -> None:
        def invalidate(payload):
            target = next(
                item for item in payload["slots"]
                if item["claim_mode"] == "ranked_observation"
            )
            target["requested_superlative_metric"] = "sales_quantity"
            return payload

        candidate, provider = _candidate("Q02", plan_mutator=invalidate)
        outcome = candidate.run_turn(
            session_id="SESSION-v233-invalid-q02",
            turn_id="TURN-002",
            question=load_frozen_questions()["Q02"]["question"],
            result_root="results/raw/v2_3_3_invalid_test",
        )
        self.assertEqual(outcome.status, "failed")
        self.assertEqual(outcome.error_stage, "claim_plan_validation")
        self.assertEqual(outcome.model_response_count, 2)
        self.assertEqual(len(provider.requests), 2)
        self.assertEqual(candidate.response_limit_snapshot().attempted, 2)
        self.assertFalse(candidate.claim_plan_trace[0].final_report_request_sent)
        self.assertNotIn(
            "final_report_from_validated_claim_plan",
            candidate.transport_audit_payload()["request_phases"],
        )


if __name__ == "__main__":
    unittest.main()
