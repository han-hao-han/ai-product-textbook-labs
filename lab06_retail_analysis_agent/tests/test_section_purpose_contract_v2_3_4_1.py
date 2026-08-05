from __future__ import annotations

import unittest

from src.deepseek_section_purpose_transport_mock_v2_3_4_1 import (
    OfflineDeepSeekProviderV2_3_4_1, SectionPurposeLogicalClientV2_3_4_1,
)
from src.fixed_question_validation import load_frozen_questions, validate_fixed_question
from src.mock_h2_registry import FrozenH2MockRegistry
from src.mock_native_tool_client_v2_1_revision import FrozenQuestionNativeToolMockClient
from src.online_native_tool_candidate_v2_3_4_1 import NativeToolOnlineCandidateV2_3_4_1
from src.section_purpose_contract_v2_3_4_1 import SectionPurposeCatalogV2_3_4_1


EXPECTED_RESPONSES = {
    "Q01": 3, "Q02": 3, "Q03": 3, "Q04": 3, "Q05": 4,
    "Q06": 4, "Q07": 4, "Q08": 1, "Q09": 1, "Q10": 1,
}


def _candidate(question_id: str, *, selection_mutator=None, report_mutator=None):
    logical = SectionPurposeLogicalClientV2_3_4_1(
        FrozenQuestionNativeToolMockClient(), selection_mutator=selection_mutator,
        report_mutator=report_mutator,
    )
    provider = OfflineDeepSeekProviderV2_3_4_1(logical)
    candidate = NativeToolOnlineCandidateV2_3_4_1(
        api_key="offline-v2341-key", registry=FrozenH2MockRegistry(),
        response_limit=EXPECTED_RESPONSES[question_id], transport=provider,
    )
    return candidate, provider


class SectionPurposeContractV2_3_4_1Tests(unittest.TestCase):
    def test_q01_q10_mock_end_to_end(self) -> None:
        questions = load_frozen_questions()
        for question_id, expected in EXPECTED_RESPONSES.items():
            with self.subTest(question_id=question_id):
                candidate, provider = _candidate(question_id)
                outcome = candidate.run_turn(
                    session_id=f"SESSION-v2341-{question_id.lower()}",
                    turn_id=f"TURN-{int(question_id[1:]):03d}",
                    question=questions[question_id]["question"],
                    result_root="results/raw/v2_3_4_1_mock_test",
                )
                fixed = validate_fixed_question(question_id, outcome)
                self.assertEqual(
                    fixed.status, "passed_deterministic_pending_manual_review", fixed.issues
                )
                snapshot = candidate.response_limit_snapshot()
                self.assertEqual((snapshot.attempted, snapshot.completed, snapshot.failed), (expected, expected, 0))
                self.assertEqual(len(provider.requests), expected)
                if question_id <= "Q07":
                    self.assertEqual(candidate.atom_selection_trace[0].status, "passed")
                    self.assertEqual(
                        candidate.transport_audit_payload()["request_phases"][-2:],
                        ["section_purpose_atom_selection", "final_report_from_section_purpose_slots"],
                    )

    def test_catalog_uses_request_type_not_output_phase(self) -> None:
        self.assertIn("request_type", SectionPurposeCatalogV2_3_4_1.model_fields)
        self.assertNotIn("phase", SectionPurposeCatalogV2_3_4_1.model_fields)

    def test_missing_key_finding_atom_is_rejected(self) -> None:
        def invalidate(payload):
            payload["selections"][1]["atom_ids"].pop()
            return payload
        candidate, _ = _candidate("Q02", selection_mutator=invalidate)
        outcome = candidate.run_turn(
            session_id="SESSION-v2341-missing", turn_id="TURN-002",
            question=load_frozen_questions()["Q02"]["question"],
            result_root="results/raw/v2_3_4_1_missing_test",
        )
        self.assertEqual(outcome.error_stage, "atom_selection_validation")
        self.assertEqual(outcome.model_response_count, 2)

    def test_partial_optional_group_is_rejected(self) -> None:
        def invalidate(payload):
            payload["selections"][2]["atom_ids"] = [payload["selections"][1]["atom_ids"][0]]
            return payload
        candidate, _ = _candidate("Q02", selection_mutator=invalidate)
        outcome = candidate.run_turn(
            session_id="SESSION-v2341-partial", turn_id="TURN-002",
            question=load_frozen_questions()["Q02"]["question"],
            result_root="results/raw/v2_3_4_1_partial_test",
        )
        self.assertEqual(outcome.error_stage, "atom_selection_validation")

    def test_policy_atom_in_advice_slot_is_rejected(self) -> None:
        def invalidate(payload):
            payload["selections"][4]["atom_ids"] = [payload["selections"][5]["atom_ids"][0]]
            return payload
        candidate, _ = _candidate("Q02", selection_mutator=invalidate)
        outcome = candidate.run_turn(
            session_id="SESSION-v2341-policy", turn_id="TURN-002",
            question=load_frozen_questions()["Q02"]["question"],
            result_root="results/raw/v2_3_4_1_policy_test",
        )
        self.assertEqual(outcome.error_stage, "atom_selection_validation")

    def test_cross_slot_report_borrowing_remains_rejected(self) -> None:
        def invalidate(payload):
            evidence = payload["report"]["sections"][1]["claims"][0]["evidence"][0]
            payload["report"]["sections"][4]["claims"][0]["evidence"].append(evidence)
            return payload
        candidate, _ = _candidate("Q02", report_mutator=invalidate)
        outcome = candidate.run_turn(
            session_id="SESSION-v2341-borrow", turn_id="TURN-002",
            question=load_frozen_questions()["Q02"]["question"],
            result_root="results/raw/v2_3_4_1_borrow_test",
        )
        self.assertEqual(outcome.error_stage, "slot_report_binding_validation")
        self.assertEqual(outcome.model_response_count, 3)


if __name__ == "__main__":
    unittest.main()
