from __future__ import annotations

import unittest

from src.deepseek_frozen_six_slot_transport_mock_v2_3_4 import (
    FrozenSixSlotLogicalClientV2_3_4,
    OfflineDeepSeekProviderV2_3_4,
)
from src.fixed_question_validation import load_frozen_questions, validate_fixed_question
from src.mock_h2_registry import FrozenH2MockRegistry
from src.mock_native_tool_client_v2_1_revision import FrozenQuestionNativeToolMockClient
from src.online_native_tool_candidate_v2_3_4 import NativeToolOnlineCandidateV2_3_4
from src.frozen_six_slot_atom_selection_v2_3_4 import SELECTION_INSTRUCTION


EXPECTED_RESPONSES = {
    "Q01": 3, "Q02": 3, "Q03": 3, "Q04": 3, "Q05": 4,
    "Q06": 4, "Q07": 4, "Q08": 1, "Q09": 1, "Q10": 1,
}


def _candidate(question_id: str, *, selection_mutator=None, report_mutator=None):
    logical = FrozenSixSlotLogicalClientV2_3_4(
        FrozenQuestionNativeToolMockClient(), selection_mutator=selection_mutator,
        report_mutator=report_mutator,
    )
    provider = OfflineDeepSeekProviderV2_3_4(logical)
    candidate = NativeToolOnlineCandidateV2_3_4(
        api_key="offline-v234-integrated-key",
        registry=FrozenH2MockRegistry(),
        response_limit=EXPECTED_RESPONSES[question_id],
        transport=provider,
    )
    return candidate, provider


class OnlineNativeToolCandidateV2_3_4Tests(unittest.TestCase):
    def test_json_object_provider_word_is_explicit(self) -> None:
        self.assertIn("json", SELECTION_INSTRUCTION.lower())

    def test_q01_q10_integrated_mock_end_to_end(self) -> None:
        questions = load_frozen_questions()
        for question_id, expected in EXPECTED_RESPONSES.items():
            with self.subTest(question_id=question_id):
                candidate, provider = _candidate(question_id)
                outcome = candidate.run_turn(
                    session_id=f"SESSION-v234-{question_id.lower()}",
                    turn_id=f"TURN-{int(question_id[1:]):03d}",
                    question=questions[question_id]["question"],
                    result_root="results/raw/v2_3_4_integrated_test",
                )
                fixed = validate_fixed_question(question_id, outcome)
                self.assertEqual(
                    fixed.status, "passed_deterministic_pending_manual_review", fixed.issues
                )
                snapshot = candidate.response_limit_snapshot()
                self.assertEqual((snapshot.attempted, snapshot.completed, snapshot.failed), (expected, expected, 0))
                self.assertEqual(len(provider.requests), expected)
                if question_id <= "Q07":
                    self.assertEqual(len(candidate.atom_selection_trace), 1)
                    self.assertEqual(candidate.atom_selection_trace[0].status, "passed")
                    self.assertEqual(candidate.atom_selection_trace[0].slot_count, 6)
                    self.assertEqual(
                        candidate.transport_audit_payload()["request_phases"][-2:],
                        ["frozen_slot_atom_selection", "final_report_from_validated_frozen_slots"],
                    )
                else:
                    self.assertEqual(candidate.atom_selection_trace, ())

    def test_unknown_atom_stops_q02_before_final_report(self) -> None:
        def invalidate(payload):
            payload["selections"][1]["atom_ids"].append("ATOM-999")
            return payload

        candidate, provider = _candidate("Q02", selection_mutator=invalidate)
        outcome = candidate.run_turn(
            session_id="SESSION-v234-invalid-q02", turn_id="TURN-002",
            question=load_frozen_questions()["Q02"]["question"],
            result_root="results/raw/v2_3_4_invalid_test",
        )
        self.assertEqual(outcome.status, "failed")
        self.assertEqual(outcome.error_stage, "atom_selection_validation")
        self.assertEqual(outcome.model_response_count, 2)
        self.assertEqual(len(provider.requests), 2)
        self.assertFalse(candidate.atom_selection_trace[0].final_report_request_sent)

    def test_extra_claim_text_is_rejected_by_strict_schema(self) -> None:
        def invalidate(payload):
            payload["selections"][0]["claim_text"] = "not allowed"
            return payload

        candidate, _ = _candidate("Q02", selection_mutator=invalidate)
        outcome = candidate.run_turn(
            session_id="SESSION-v234-extra-field", turn_id="TURN-002",
            question=load_frozen_questions()["Q02"]["question"],
            result_root="results/raw/v2_3_4_extra_field_test",
        )
        self.assertEqual(outcome.error_stage, "atom_selection_validation")
        self.assertEqual(outcome.model_response_count, 2)

    def test_reordered_slots_are_rejected(self) -> None:
        def invalidate(payload):
            payload["selections"][1], payload["selections"][2] = (
                payload["selections"][2], payload["selections"][1]
            )
            return payload

        candidate, _ = _candidate("Q02", selection_mutator=invalidate)
        outcome = candidate.run_turn(
            session_id="SESSION-v234-reordered", turn_id="TURN-002",
            question=load_frozen_questions()["Q02"]["question"],
            result_root="results/raw/v2_3_4_reordered_test",
        )
        self.assertEqual(outcome.error_stage, "atom_selection_validation")

    def test_missing_global_fact_is_rejected(self) -> None:
        def invalidate(payload):
            target = next(item for item in payload["selections"] if item["atom_ids"] and item["slot_id"] in {"SLOT-002", "SLOT-003", "SLOT-004"})
            target["atom_ids"].pop()
            return payload

        candidate, _ = _candidate("Q02", selection_mutator=invalidate)
        outcome = candidate.run_turn(
            session_id="SESSION-v234-missing-fact", turn_id="TURN-002",
            question=load_frozen_questions()["Q02"]["question"],
            result_root="results/raw/v2_3_4_missing_fact_test",
        )
        self.assertEqual(outcome.error_stage, "atom_selection_validation")

    def test_duplicate_fact_assignment_is_rejected(self) -> None:
        def invalidate(payload):
            atom_id = payload["selections"][1]["atom_ids"][0]
            payload["selections"][2]["atom_ids"].append(atom_id)
            return payload

        candidate, _ = _candidate("Q02", selection_mutator=invalidate)
        outcome = candidate.run_turn(
            session_id="SESSION-v234-duplicate-fact", turn_id="TURN-002",
            question=load_frozen_questions()["Q02"]["question"],
            result_root="results/raw/v2_3_4_duplicate_fact_test",
        )
        self.assertEqual(outcome.error_stage, "atom_selection_validation")
        self.assertEqual(outcome.model_response_count, 2)

    def test_cross_slot_report_evidence_is_rejected_before_formal_validator(self) -> None:
        def invalidate(payload):
            borrowed = payload["report"]["sections"][5]["claims"][0]["evidence"][0]
            payload["report"]["sections"][4]["claims"][0]["evidence"].append(borrowed)
            return payload

        candidate, _ = _candidate("Q02", report_mutator=invalidate)
        outcome = candidate.run_turn(
            session_id="SESSION-v234-cross-slot", turn_id="TURN-002",
            question=load_frozen_questions()["Q02"]["question"],
            result_root="results/raw/v2_3_4_cross_slot_test",
        )
        self.assertEqual(outcome.error_stage, "slot_report_binding_validation")
        self.assertEqual(outcome.model_response_count, 3)

    def test_call_id_in_report_prose_is_rejected(self) -> None:
        def invalidate(payload):
            payload["report"]["sections"][2]["claims"][0]["statement"] += " CALL-001"
            return payload

        candidate, _ = _candidate("Q02", report_mutator=invalidate)
        outcome = candidate.run_turn(
            session_id="SESSION-v234-call-id", turn_id="TURN-002",
            question=load_frozen_questions()["Q02"]["question"],
            result_root="results/raw/v2_3_4_call_id_test",
        )
        self.assertEqual(outcome.error_stage, "slot_report_binding_validation")


if __name__ == "__main__":
    unittest.main()
