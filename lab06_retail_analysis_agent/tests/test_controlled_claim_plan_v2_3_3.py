from __future__ import annotations

import json
import unittest
from dataclasses import replace
from typing import Any

from pydantic import ValidationError

from src.claim_evidence_bundles_v2_3_2 import ClaimEvidenceEnvelopeV2_3_2
from src.controlled_claim_plan_mock_v2_3_3 import (
    mock_model_claim_plan,
    mock_model_final_report,
)
from src.controlled_claim_plan_v2_3_3 import (
    ClaimPlanDraftV2_3_3,
    ClaimPlanValidationError,
    validate_claim_plan,
)
from src.deepseek_report_terminal_transport_mock_v2_3_2 import (
    BundleAwareLogicalClientV2_3_2,
    OfflineDeepSeekProviderV2_3_2,
)
from src.fixed_question_validation import load_frozen_questions, validate_fixed_question
from src.mock_h2_registry import FrozenH2MockRegistry
from src.mock_native_tool_client_v2_1_revision import FrozenQuestionNativeToolMockClient
from src.online_native_tool_candidate_v2_3_2 import NativeToolOnlineCandidateV2_3_2
from src.report_validation import validate_report


EXPECTED_RESPONSES = {
    "Q01": 2, "Q02": 2, "Q03": 2, "Q04": 2, "Q05": 3,
    "Q06": 3, "Q07": 3, "Q08": 1, "Q09": 1, "Q10": 1,
}


class CapturingProvider(OfflineDeepSeekProviderV2_3_2):
    def __init__(self, logical_client: Any):
        super().__init__(logical_client)
        self.payloads: list[dict[str, Any]] = []

    def __call__(self, url, body, headers, timeout_seconds):
        self.payloads.append(json.loads(body.decode("utf-8")))
        return super().__call__(url, body, headers, timeout_seconds)


def _run(question_id: str):
    provider = CapturingProvider(
        BundleAwareLogicalClientV2_3_2(FrozenQuestionNativeToolMockClient())
    )
    candidate = NativeToolOnlineCandidateV2_3_2(
        api_key="offline-v233-test-key",
        registry=FrozenH2MockRegistry(),
        response_limit=EXPECTED_RESPONSES[question_id],
        transport=provider,
    )
    outcome = candidate.run_turn(
        session_id=f"SESSION-v233-{question_id.lower()}",
        turn_id=f"TURN-{int(question_id[1:]):03d}",
        question=load_frozen_questions()[question_id]["question"],
        result_root="results/raw/v2_3_3_test_only",
    )
    return outcome, provider


def _envelope(provider: CapturingProvider) -> ClaimEvidenceEnvelopeV2_3_2:
    return ClaimEvidenceEnvelopeV2_3_2.model_validate_json(
        provider.payloads[-1]["messages"][-1]["content"]
    )


class ControlledClaimPlanV2_3_3Tests(unittest.TestCase):
    def test_q01_q10_offline_pipeline_keeps_current_harness_green(self) -> None:
        for question_id in EXPECTED_RESPONSES:
            with self.subTest(question_id=question_id):
                outcome, provider = _run(question_id)
                if question_id <= "Q07":
                    source = _envelope(provider)
                    draft = mock_model_claim_plan(source)
                    validated = validate_claim_plan(draft, source)
                    final = mock_model_final_report(validated)
                    report_validation = validate_report(
                        final.report,
                        list(outcome.facts),
                        list(outcome.request_records),
                        list(outcome.policy_records),
                    )
                    self.assertEqual(report_validation.status, "passed", report_validation.issues)
                    outcome = replace(
                        outcome,
                        report_draft=final.report,
                        report_validation=report_validation,
                    )
                fixed = validate_fixed_question(question_id, outcome)
                self.assertEqual(
                    fixed.status,
                    "passed_deterministic_pending_manual_review",
                    fixed.issues,
                )

    def test_q02_selection_atom_derives_fact_001_permission(self) -> None:
        _, provider = _run("Q02")
        source = _envelope(provider)
        validated = validate_claim_plan(mock_model_claim_plan(source), source)
        selection_slots = [
            slot for slot in validated.slots
            if slot.allowed_selection_limit_values == ["5"]
        ]
        self.assertTrue(selection_slots)
        self.assertTrue(any(
            getattr(item, "fact_id", None) == "FACT-001"
            for slot in selection_slots for item in slot.allowed_evidence
        ))

    def test_q02_quantity_superlative_without_quantity_rank_fails_closed(self) -> None:
        _, provider = _run("Q02")
        source = _envelope(provider)
        draft = mock_model_claim_plan(source)
        payload = draft.model_dump(mode="json")
        target = next(item for item in payload["slots"] if item["claim_mode"] == "ranked_observation")
        target["requested_superlative_metric"] = "sales_quantity"
        drifted = ClaimPlanDraftV2_3_3.model_validate(payload)
        with self.assertRaisesRegex(ClaimPlanValidationError, "matching rank=1"):
            validate_claim_plan(drifted, source)

    def test_unknown_ids_and_program_authored_claim_text_are_rejected(self) -> None:
        _, provider = _run("Q02")
        source = _envelope(provider)
        payload = mock_model_claim_plan(source).model_dump(mode="json")
        payload["slots"][0]["atom_ids"][0] = "ATOM-999"
        unknown = ClaimPlanDraftV2_3_3.model_validate(payload)
        with self.assertRaisesRegex(ClaimPlanValidationError, "unknown atom"):
            validate_claim_plan(unknown, source)

        payload = mock_model_claim_plan(source).model_dump(mode="json")
        payload["slots"][0]["claim_text"] = "前五商品"
        with self.assertRaises(ValidationError):
            ClaimPlanDraftV2_3_3.model_validate(payload)


if __name__ == "__main__":
    unittest.main()
