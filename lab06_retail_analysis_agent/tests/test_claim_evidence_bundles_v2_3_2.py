from __future__ import annotations

import json
import unittest
from typing import Any

from pydantic import ValidationError

from src.claim_evidence_bundles_v2_3_2 import (
    ClaimEvidenceEnvelopeV2_3_2,
    build_claim_evidence_bundles,
)
from src.deepseek_report_terminal_transport_mock_v2_3_2 import (
    BundleAwareLogicalClientV2_3_2,
    OfflineDeepSeekProviderV2_3_2,
)
from src.fixed_question_validation import (
    load_frozen_questions,
    validate_fixed_question,
)
from src.mock_h2_registry import FrozenH2MockRegistry
from src.mock_native_tool_client_v2_1_revision import (
    FrozenQuestionNativeToolMockClient,
)
from src.online_native_tool_candidate_v2_3_2 import (
    NativeToolOnlineCandidateV2_3_2,
)
from src.report_admissible_evidence_projection_v2_3_1 import (
    ReportAdmissibleEnvelopeV2_3_1,
)


EXPECTED_RESPONSES = {
    "Q01": 2,
    "Q02": 2,
    "Q03": 2,
    "Q04": 2,
    "Q05": 3,
    "Q06": 3,
    "Q07": 3,
    "Q08": 1,
    "Q09": 1,
    "Q10": 1,
}


class CapturingProviderV2_3_2(OfflineDeepSeekProviderV2_3_2):
    def __init__(self, logical_client: Any):
        super().__init__(logical_client)
        self.outbound_payloads: list[dict[str, Any]] = []

    def __call__(self, url, body, headers, timeout_seconds):
        self.outbound_payloads.append(json.loads(body.decode("utf-8")))
        return super().__call__(url, body, headers, timeout_seconds)


class ClaimEvidenceBundlesV2_3_2Tests(unittest.TestCase):
    def _run(self, question_id: str):
        provider = CapturingProviderV2_3_2(
            BundleAwareLogicalClientV2_3_2(
                FrozenQuestionNativeToolMockClient()
            )
        )
        candidate = NativeToolOnlineCandidateV2_3_2(
            api_key="offline-v2-3-2-test-key",
            registry=FrozenH2MockRegistry(),
            response_limit=EXPECTED_RESPONSES[question_id],
            transport=provider,
        )
        outcome = candidate.run_turn(
            session_id=f"SESSION-v232-{question_id.lower()}",
            turn_id=f"TURN-{int(question_id[1:]):03d}",
            question=load_frozen_questions()[question_id]["question"],
            result_root="results/raw/v2_3_2_test_only",
        )
        return outcome, candidate, provider

    @staticmethod
    def _terminal_envelope(
        provider: CapturingProviderV2_3_2,
    ) -> ClaimEvidenceEnvelopeV2_3_2:
        content = provider.outbound_payloads[-1]["messages"][-1]["content"]
        return ClaimEvidenceEnvelopeV2_3_2.model_validate_json(content)

    def test_q01_q10_bundle_aware_mock_end_to_end(self) -> None:
        for question_id, expected_count in EXPECTED_RESPONSES.items():
            with self.subTest(question_id=question_id):
                outcome, candidate, provider = self._run(question_id)
                validation = validate_fixed_question(question_id, outcome)
                self.assertEqual(
                    validation.status,
                    "passed_deterministic_pending_manual_review",
                )
                self.assertEqual(len(provider.requests), expected_count)
                self.assertEqual(candidate.last_trace[-1].visible_tool_names, ())
                if question_id <= "Q07":
                    envelope = self._terminal_envelope(provider)
                    self.assertTrue(envelope.claim_evidence_bundles)
                    self.assertFalse(
                        envelope.bundle_usage_contract.bundle_ids_allowed_in_report
                    )

    def test_q02_selection_limit_bundle_binds_fact_001(self) -> None:
        _, _, provider = self._run("Q02")
        envelope = self._terminal_envelope(provider)
        selection = [
            item
            for item in envelope.claim_evidence_bundles
            if item.bundle_kind == "selection_limit"
        ]
        self.assertEqual(len(selection), 1)
        atom = selection[0].support_atoms[0]
        self.assertEqual(atom.semantic_role, "selection_limit")
        self.assertEqual(atom.value, "5")
        self.assertEqual(atom.evidence_ids, ["FACT-001"])
        ranked = [
            item
            for item in envelope.claim_evidence_bundles
            if item.bundle_kind == "ranked_entity"
        ]
        self.assertEqual([item.subject.rank for item in ranked], [1, 2, 3, 4, 5])

    def test_q06_cross_tool_dependency_is_generic_and_exact(self) -> None:
        _, _, provider = self._run("Q06")
        envelope = self._terminal_envelope(provider)
        cross = [
            item
            for item in envelope.claim_evidence_bundles
            if item.bundle_kind == "cross_tool_observation"
        ]
        self.assertEqual(len(cross), 1)
        self.assertEqual(cross[0].source_tool_names, ["analyze_time_trend", "rank_products"])
        self.assertEqual(len(cross[0].support_atoms[0].evidence_ids), 2)

        v231 = ReportAdmissibleEnvelopeV2_3_1(
            phase="report_terminal_admissible_evidence",
            session_id=envelope.session_id,
            turn_id=envelope.turn_id,
            tool_evidence=envelope.tool_evidence,
        )
        second = v231.tool_evidence[1]
        drifted_facts = [
            item.model_copy(update={"start_date": "2011-10-01"})
            for item in second.fact_references
        ]
        drifted_calls = [
            v231.tool_evidence[0],
            second.model_copy(update={"fact_references": drifted_facts}),
        ]
        drifted = v231.model_copy(update={"tool_evidence": drifted_calls})
        self.assertFalse(
            any(
                item.bundle_kind == "cross_tool_observation"
                for item in build_claim_evidence_bundles(drifted)
            )
        )

    def test_unknown_evidence_and_program_authored_claim_text_fail_closed(self) -> None:
        _, _, provider = self._run("Q02")
        payload = self._terminal_envelope(provider).model_dump(mode="json")
        payload["claim_evidence_bundles"][0]["support_atoms"][0][
            "evidence_ids"
        ] = ["FACT-999"]
        with self.assertRaises(ValidationError):
            ClaimEvidenceEnvelopeV2_3_2.model_validate(payload)

        payload = self._terminal_envelope(provider).model_dump(mode="json")
        payload["claim_evidence_bundles"][0]["claim_text"] = "前5商品"
        with self.assertRaises(ValidationError):
            ClaimEvidenceEnvelopeV2_3_2.model_validate(payload)


if __name__ == "__main__":
    unittest.main()
