from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from src.deepseek_report_terminal_transport_mock_v2_3_1 import (
    OfflineDeepSeekProviderV2_3_1,
    ReportAdmissibleLogicalClientV2_3_1,
)
from src.deepseek_report_terminal_transport_v2_3 import STANDARD_URL
from src.fixed_question_validation import (
    load_frozen_questions,
    validate_fixed_question,
)
from src.mock_h2_registry import FrozenH2MockRegistry
from src.mock_native_tool_client_v2_1_revision import (
    FrozenQuestionNativeToolMockClient,
)
from src.online_native_tool_candidate_v2_3_1 import (
    NativeToolOnlineCandidateV2_3_1,
)
from src.report_admissible_evidence_projection_v2_3_1 import (
    FORBIDDEN_TERMINAL_KEYS,
    ReportAdmissibleEnvelopeV2_3_1,
)
from src.report_validation import (
    REPORT_SECTION_ORDER,
    ReportClaim,
    ReportDraft,
    ReportSection,
    fact_reference,
    validate_report,
)
from src.batch_a_safe_runner_v2_3_1 import execute_batch_a_v2_3_1
from src.q01_q10_batch_a_safe_runner import (
    BATCH_A_OFFLINE_CONFIRMATION,
    validate_offline_execution_request,
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


def _walk_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(
            key for item in value.values() for key in _walk_keys(item)
        )
    if isinstance(value, list):
        return {key for item in value for key in _walk_keys(item)}
    return set()


class CapturingProvider(OfflineDeepSeekProviderV2_3_1):
    outbound_payloads: list[dict[str, Any]]

    def __init__(self, logical_client: Any):
        super().__init__(logical_client)
        self.outbound_payloads = []

    def __call__(self, url, body, headers, timeout_seconds):
        self.outbound_payloads.append(json.loads(body.decode("utf-8")))
        return super().__call__(url, body, headers, timeout_seconds)


class ReportAdmissibleEvidenceProjectionV2_3_1Tests(unittest.TestCase):
    def _run(self, question_id: str):
        logical = ReportAdmissibleLogicalClientV2_3_1(
            FrozenQuestionNativeToolMockClient()
        )
        provider = CapturingProvider(logical)
        candidate = NativeToolOnlineCandidateV2_3_1(
            api_key="offline-v2-3-1-test-key",
            registry=FrozenH2MockRegistry(),
            response_limit=EXPECTED_RESPONSES[question_id],
            transport=provider,
        )
        outcome = candidate.run_turn(
            session_id=f"SESSION-v231-{question_id.lower()}",
            turn_id=f"TURN-{int(question_id[1:]):03d}",
            question=load_frozen_questions()[question_id]["question"],
            result_root="results/raw/v2_3_1_test_only",
        )
        return outcome, candidate, provider

    def test_q01_q10_terminal_wire_and_current_harness_pass(self) -> None:
        for question_id in EXPECTED_RESPONSES:
            with self.subTest(question_id=question_id):
                outcome, candidate, provider = self._run(question_id)
                validation = validate_fixed_question(question_id, outcome)
                self.assertIn(
                    validation.status,
                    {
                        "protocol_and_dataflow_passed",
                        "passed_deterministic_pending_manual_review",
                    },
                )
                terminal = provider.outbound_payloads[-1]
                self.assertEqual(provider.requests[-1].endpoint, STANDARD_URL)
                self.assertNotIn("tools", terminal)
                self.assertNotIn("tool_choice", terminal)
                self.assertEqual(
                    terminal["response_format"], {"type": "json_object"}
                )
                self.assertEqual(candidate.last_trace[-1].visible_tool_names, ())
                if question_id <= "Q07":
                    envelope_payload = json.loads(
                        terminal["messages"][-1]["content"]
                    )
                    envelope = ReportAdmissibleEnvelopeV2_3_1.model_validate(
                        envelope_payload
                    )
                    self.assertEqual(
                        envelope.phase,
                        "report_terminal_admissible_evidence",
                    )
                    self.assertFalse(
                        _walk_keys(envelope_payload["tool_evidence"])
                        & FORBIDDEN_TERMINAL_KEYS
                    )
                    for call in envelope.tool_evidence:
                        self.assertTrue(call.fact_references)
                        self.assertEqual(
                            set(call.model_dump()),
                            {
                                "internal_call_id",
                                "tool_name",
                                "fact_references",
                                "request_references",
                                "policy_references",
                            },
                        )

    def test_q02_projection_removes_observed_internal_row_count(self) -> None:
        _, _, provider = self._run("Q02")
        terminal_text = json.dumps(
            provider.outbound_payloads[-1],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        self.assertNotIn("row_count", terminal_text)
        self.assertNotIn("524878", terminal_text)
        self.assertNotIn("analysis_scope", terminal_text)
        self.assertNotIn("source_result_path", terminal_text)

    def test_claims_cannot_borrow_rank_or_top_n_from_other_claims(self) -> None:
        outcome, _, _ = self._run("Q02")
        rank_three = next(fact for fact in outcome.facts if fact.rank == 3)
        rank_five = next(fact for fact in outcome.facts if fact.rank == 5)
        local_claims = [
            ReportClaim(statement="排名第3。", evidence=[]),
            ReportClaim(
                statement="3。",
                evidence=[fact_reference(rank_three)],
            ),
            ReportClaim(statement="前5。", evidence=[]),
            ReportClaim(
                statement="5。",
                evidence=[fact_reference(rank_five)],
            ),
        ]
        sections = []
        for index, name in enumerate(REPORT_SECTION_ORDER):
            claims = (
                local_claims
                if index == 0
                else [ReportClaim(statement="没有新增结论。", evidence=[])]
            )
            sections.append(ReportSection(name=name, claims=claims))
        draft = ReportDraft(
            schema_version="1.5.6-h3-report-draft-v1",
            session_id=outcome.session_id,
            turn_id=outcome.turn_id,
            title="局部证据负例",
            sections=sections,
        )
        validation = validate_report(
            draft,
            list(outcome.facts),
            list(outcome.request_records),
            list(outcome.policy_records),
        )
        unsupported = [
            issue
            for issue in validation.issues
            if issue.code == "untraceable_numeric_token"
        ]
        self.assertEqual(validation.status, "failed")
        self.assertTrue(any("3" in issue.message for issue in unsupported))
        self.assertTrue(any("5" in issue.message for issue in unsupported))

    def test_unsupported_arithmetic_inference_remains_rejected(self) -> None:
        outcome, _, _ = self._run("Q02")
        evidence = [fact_reference(item) for item in outcome.facts[:2]]
        sections = [
            ReportSection(
                name=name,
                claims=[
                    ReportClaim(
                        statement=(
                            "平均客单价为123.45英镑。"
                            if index == 0
                            else "没有新增结论。"
                        ),
                        evidence=evidence if index == 0 else [],
                    )
                ],
            )
            for index, name in enumerate(REPORT_SECTION_ORDER)
        ]
        draft = ReportDraft(
            schema_version="1.5.6-h3-report-draft-v1",
            session_id=outcome.session_id,
            turn_id=outcome.turn_id,
            title="算术推断负例",
            sections=sections,
        )
        validation = validate_report(draft, list(outcome.facts))
        self.assertEqual(validation.status, "failed")
        self.assertTrue(
            any(
                issue.code == "untraceable_numeric_token"
                and "123.45" in issue.message
                for issue in validation.issues
            )
        )

    def test_batch_runner_accepts_hidden_tools_only_on_terminal_step(self) -> None:
        provider = OfflineDeepSeekProviderV2_3_1(
            ReportAdmissibleLogicalClientV2_3_1(
                FrozenQuestionNativeToolMockClient()
            )
        )
        authority = validate_offline_execution_request(
            confirmation=BATCH_A_OFFLINE_CONFIRMATION
        )
        with tempfile.TemporaryDirectory() as temporary:
            result = execute_batch_a_v2_3_1(
                api_key="offline-v2-3-1-batch-key",
                registry=FrozenH2MockRegistry(),
                transport=provider,
                authority=authority,
                output_parent=Path(temporary),
            )
        self.assertTrue(result.passed)
        self.assertTrue(
            all(not case["program_failures"] for case in result.cases)
        )


if __name__ == "__main__":
    unittest.main()
