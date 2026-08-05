from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from src.claim_controller_v3_real_runner import (
    FULL_CAP,
    FULL_ORDER,
    execute_validation_v3_full,
)
from src.claim_level_report_controller_mock_v3 import ClaimLevelLogicalClientV3
from src.claim_level_report_controller_v3 import ClaimStatementResponseV3
from src.deepseek_internal_call_isolation_transport_mock_v2_3_4_2 import (
    CallIsolatedFrozenQuestionNativeToolMockClient,
    OfflineDeepSeekProviderV2_3_4_2,
)
from src.fixed_question_validation import load_frozen_questions, validate_fixed_question
from src.mock_h2_registry import FrozenH2MockRegistry
from src.online_native_tool_candidate_claim_controller_v3 import (
    COMBINED_PROMPT_VERSION,
    NativeToolOnlineCandidateClaimControllerV3,
)
from src.tool_routing_prompt_v1_real_runner import ToolRoutingAuthority


EXPECTED_RESPONSES = {
    "Q01": 3, "Q02": 3, "Q03": 3, "Q04": 3, "Q05": 4,
    "Q06": 4, "Q07": 4, "Q08": 1, "Q09": 1, "Q10": 1,
}


def _candidate(question_id: str, *, claim_mutator=None):
    logical = ClaimLevelLogicalClientV3(
        CallIsolatedFrozenQuestionNativeToolMockClient(),
        claim_mutator=claim_mutator,
    )
    provider = OfflineDeepSeekProviderV2_3_4_2(logical)
    candidate = NativeToolOnlineCandidateClaimControllerV3(
        api_key="offline-v3-key",
        registry=FrozenH2MockRegistry(),
        response_limit=EXPECTED_RESPONSES[question_id] + 1,
        transport=provider,
    )
    return candidate, provider


class ClaimLevelReportControllerV3Tests(unittest.TestCase):
    def _run(self, question_id: str, **kwargs):
        candidate, provider = _candidate(question_id, **kwargs)
        outcome = candidate.run_turn(
            session_id=f"SESSION-v3-{question_id.lower()}",
            turn_id=f"TURN-{int(question_id[1:]):03d}",
            question=load_frozen_questions()[question_id]["question"],
            result_root="results/raw/claim_controller_v3_test",
        )
        return candidate, provider, outcome

    def test_q01_plan_makes_previously_missing_incomplete_period_mandatory(self) -> None:
        candidate, _, outcome = self._run("Q01")
        self.assertEqual(
            validate_fixed_question("Q01", outcome).status,
            "passed_deterministic_pending_manual_review",
        )
        trace = candidate.terminal_protocol_trace[-1]
        plan = trace["model_visible_claim_plan"]
        result_claims = [item for item in plan["claims"] if item["slot_id"] == "SLOT-002"]
        self.assertTrue(any("2011-12" in item["required_literals"] for item in result_claims))
        mapped = trace["mapped_program_response"]
        result_section = mapped["report"]["sections"][1]
        self.assertTrue(any(
            any(ref.get("fact_id") == "FACT-007" for ref in claim["evidence"])
            for claim in result_section["claims"]
        ))

    def test_q07_preserves_raw_ratio_literals(self) -> None:
        candidate, _, outcome = self._run("Q07")
        self.assertEqual(
            validate_fixed_question("Q07", outcome).status,
            "passed_deterministic_pending_manual_review",
        )
        plan = candidate.terminal_protocol_trace[-1]["model_visible_claim_plan"]
        literals = {
            literal
            for item in plan["claims"]
            if item["slot_id"] == "SLOT-002"
            for literal in item["required_literals"]
        }
        self.assertIn("0.748159", literals)
        self.assertIn("0.835098", literals)

    def test_model_cannot_submit_evidence_objects(self) -> None:
        payload = {
            "phase": "claim_statement_response_v3",
            "session_id": "SESSION-test",
            "turn_id": "TURN-001",
            "title": "报告",
            "claims": [
                {"claim_id": f"CLAIM-{index:03d}", "statement": "文本", "evidence": []}
                for index in range(1, 7)
            ],
            "chart_titles": [],
        }
        with self.assertRaises(ValidationError):
            ClaimStatementResponseV3.model_validate(payload)

    def test_missing_literal_gets_one_correction_then_stops_with_evidence(self) -> None:
        def omit(payload):
            payload["claims"][1]["statement"] = "遗漏冻结值。"
            return payload

        candidate, _, outcome = self._run("Q01", claim_mutator=omit)
        self.assertEqual(outcome.status, "failed")
        self.assertEqual(outcome.error_stage, "terminal_protocol_validation")
        self.assertEqual(
            [item["status"] for item in candidate.terminal_protocol_trace],
            ["repair_requested", "failed_stopped"],
        )
        self.assertEqual(candidate.response_limit_snapshot().attempted, 4)
        self.assertEqual(
            candidate.terminal_protocol_trace[-1]["error_code"],
            "deterministic_report_validation_failed",
        )

    def test_saved_q01_style_cross_claim_semantics_are_corrected_once(self) -> None:
        calls = 0

        def first_bad_then_clean(payload):
            nonlocal calls
            calls += 1
            if calls == 1:
                payload["claims"][0]["statement"] = (
                    "sales_amount_gbp，客单价及从2010-12至2011-12的结果。"
                )
                payload["claims"][5]["statement"] = "不展示原始CustomerID。"
            return payload

        candidate, _, outcome = self._run(
            "Q01", claim_mutator=first_bad_then_clean
        )
        self.assertEqual(outcome.status, "completed")
        self.assertEqual(
            [item["status"] for item in candidate.terminal_protocol_trace],
            ["repair_requested", "passed"],
        )
        issues = candidate.terminal_protocol_trace[0]["validation_issues"]
        self.assertTrue(any(item["code"] == "claim_local_numeric_token" for item in issues))

    def test_model_visible_plan_has_no_internal_call_or_source_alias(self) -> None:
        candidate, _, _ = self._run("Q06")
        serialized = json.dumps(
            candidate.terminal_protocol_trace[-1]["model_visible_claim_plan"],
            ensure_ascii=False,
        )
        self.assertNotRegex(serialized, r"CALL-\d+")
        self.assertNotRegex(serialized, r"source_[0-9a-f]+")
        plan = candidate.terminal_protocol_trace[-1]["model_visible_claim_plan"]
        self.assertTrue(all("evidence" not in item for item in plan["claims"]))

    def test_missing_dimension_literal_and_empty_evidence_metric_share_one_feedback(self) -> None:
        calls = 0

        def first_bad_then_clean(payload):
            nonlocal calls
            calls += 1
            if calls == 1:
                payload["claims"][2]["statement"] = payload["claims"][2]["statement"].replace(
                    "united_kingdom", "United Kingdom"
                )
                empty_claim = next(
                    item for item in payload["claims"] if item["claim_id"] == "CLAIM-006"
                )
                empty_claim["statement"] = "其他地区的客单价值得进一步解释。"
            return payload

        candidate, _, outcome = self._run("Q05", claim_mutator=first_bad_then_clean)
        self.assertEqual(outcome.status, "completed")
        self.assertEqual(
            [item["status"] for item in candidate.terminal_protocol_trace],
            ["repair_requested", "passed"],
        )
        codes = {
            item["code"]
            for item in candidate.terminal_protocol_trace[0]["validation_issues"]
        }
        self.assertIn("required_literal_missing", codes)
        self.assertIn("claim_local_metric_without_evidence", codes)

    def test_frozen_superlative_rule_is_preflighted_before_formal_report(self) -> None:
        calls = 0

        def first_bad_then_clean(payload):
            nonlocal calls
            calls += 1
            if calls == 1:
                payload["claims"][0]["statement"] = (
                    "sales_amount_gbp用于回答销售额最高月份。"
                )
            return payload

        candidate, _, outcome = self._run("Q04", claim_mutator=first_bad_then_clean)
        self.assertEqual(outcome.status, "completed")
        self.assertEqual(
            [item["status"] for item in candidate.terminal_protocol_trace],
            ["repair_requested", "passed"],
        )
        self.assertTrue(
            any(
                item["code"] == "unsupported_sales_amount_superlative"
                for item in candidate.terminal_protocol_trace[0]["validation_issues"]
            )
        )

    def test_q01_q10_offline_end_to_end(self) -> None:
        def transport_factory(_question_id: str):
            logical = ClaimLevelLogicalClientV3(
                CallIsolatedFrozenQuestionNativeToolMockClient()
            )
            return OfflineDeepSeekProviderV2_3_4_2(logical)

        with tempfile.TemporaryDirectory() as temp:
            result = execute_validation_v3_full(
                api_key="offline-v3-runner-key",
                registry=FrozenH2MockRegistry(),
                transport_factory=transport_factory,
                authority=ToolRoutingAuthority(
                    "offline_injected_transport", "offline-not-real"
                ),
                output_parent=Path(temp),
                run_id="claim_controller_v3_full_offline_test",
            )
            self.assertTrue(result.passed, result.summary)
            self.assertEqual(result.summary["question_ids_executed"], list(FULL_ORDER))
            self.assertEqual(result.summary["actual_response_attempts"], 27)
            self.assertEqual(result.summary["response_attempt_upper_bound"], FULL_CAP)
            self.assertEqual(
                result.summary["tool_selection_prompt_version"], COMBINED_PROMPT_VERSION
            )
            self.assertEqual(result.summary["model_visible_internal_call_values"], 0)


if __name__ == "__main__":
    unittest.main()
