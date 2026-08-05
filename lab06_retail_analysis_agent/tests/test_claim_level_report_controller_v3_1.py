from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from src.claim_controller_v3_1_real_runner import (
    FULL_CAP,
    FULL_ORDER,
    execute_validation_v3_1_full,
)
from src.claim_level_report_controller_mock_v3_1 import ClaimTemplateLogicalClientV3_1
from src.claim_level_report_controller_v3_1 import (
    CHART_TITLE_TEMPLATES,
    INTERPRETATION_TEMPLATES,
    RECOMMENDATION_TEMPLATES,
    REPORT_TITLE_TEMPLATES,
    ClaimTemplateResponseV3_1,
    build_repair_feedback_v3_1,
)
from src.deepseek_internal_call_isolation_transport_mock_v2_3_4_2 import (
    CallIsolatedFrozenQuestionNativeToolMockClient,
    OfflineDeepSeekProviderV2_3_4_2,
)
from src.fixed_question_validation import load_frozen_questions, validate_fixed_question
from src.mock_h2_registry import FrozenH2MockRegistry
from src.online_native_tool_candidate_claim_controller_v3_1 import (
    COMBINED_PROMPT_VERSION,
    NativeToolOnlineCandidateClaimControllerV3_1,
)
from src.tool_routing_prompt_v1_real_runner import ToolRoutingAuthority


EXPECTED_RESPONSES = {
    "Q01": 3, "Q02": 3, "Q03": 3, "Q04": 3, "Q05": 4,
    "Q06": 4, "Q07": 4, "Q08": 1, "Q09": 1, "Q10": 1,
}


def _candidate(question_id: str, *, mutator=None):
    logical = ClaimTemplateLogicalClientV3_1(
        CallIsolatedFrozenQuestionNativeToolMockClient(),
        template_response_mutator=mutator,
    )
    provider = OfflineDeepSeekProviderV2_3_4_2(logical)
    return NativeToolOnlineCandidateClaimControllerV3_1(
        api_key="offline-v3-1-key",
        registry=FrozenH2MockRegistry(),
        response_limit=EXPECTED_RESPONSES[question_id] + 1,
        transport=provider,
    )


class ClaimLevelReportControllerV31Tests(unittest.TestCase):
    def _run(self, question_id: str, **kwargs):
        candidate = _candidate(question_id, **kwargs)
        outcome = candidate.run_turn(
            session_id=f"SESSION-v31-{question_id.lower()}",
            turn_id=f"TURN-{int(question_id[1:]):03d}",
            question=load_frozen_questions()[question_id]["question"],
            result_root="results/raw/claim_controller_v3_1_test",
        )
        return candidate, outcome

    def test_q02_model_selects_templates_and_program_expands_all_controlled_text(self) -> None:
        candidate, outcome = self._run("Q02")
        self.assertEqual(
            validate_fixed_question("Q02", outcome).status,
            "passed_deterministic_pending_manual_review",
        )
        trace = candidate.terminal_protocol_trace[-1]
        parsed = trace["parsed_model_response"]
        self.assertNotIn("title", parsed)
        self.assertNotIn("chart_titles", parsed)
        self.assertEqual(len(parsed["template_selections"]), 2)
        mapped = trace["mapped_program_response"]
        self.assertIn(mapped["report"]["title"], REPORT_TITLE_TEMPLATES.values())
        self.assertIn(
            mapped["report"]["sections"][3]["claims"][0]["statement"],
            INTERPRETATION_TEMPLATES.values(),
        )
        self.assertIn(
            mapped["report"]["sections"][4]["claims"][0]["statement"],
            RECOMMENDATION_TEMPLATES.values(),
        )
        allowed_chart_titles = {
            title for values in CHART_TITLE_TEMPLATES.values() for title in values.values()
        }
        self.assertTrue(
            all(item["title"] in allowed_chart_titles for item in mapped["chart_requests"])
        )

    def test_saved_q02_free_text_shape_is_rejected_by_v31_schema(self) -> None:
        payload = {
            "phase": "claim_and_template_selection_response_v3_1",
            "session_id": "SESSION-test",
            "turn_id": "TURN-002",
            "report_title_template_id": "TITLE-CONTROLLED-RETAIL",
            "title": "第二个销售额报告",
            "authored_claims": [{"claim_id": "CLAIM-001", "statement": "文本"}],
            "template_selections": [
                {"claim_id": "CLAIM-002", "template_id": "INTERPRET-HISTORICAL-ONLY", "statement": "销售额解释"},
                {"claim_id": "CLAIM-003", "template_id": "RECOMMEND-HUMAN-REVIEW"},
            ],
            "chart_title_selections": [],
        }
        with self.assertRaises(ValidationError):
            ClaimTemplateResponseV3_1.model_validate(payload)

    def test_unknown_template_id_gets_one_correction_then_stops(self) -> None:
        def invalid(payload):
            payload["template_selections"][0]["template_id"] = "INTERPRET-UNFROZEN"
            return payload

        candidate, outcome = self._run("Q02", mutator=invalid)
        self.assertEqual(outcome.status, "failed")
        self.assertEqual(
            [item["status"] for item in candidate.terminal_protocol_trace],
            ["repair_requested", "failed_stopped"],
        )
        self.assertEqual(
            candidate.terminal_protocol_trace[-1]["error_code"],
            "template_selection_validation_failed",
        )

    def test_model_visible_plan_contains_ids_but_not_template_prose(self) -> None:
        candidate, _ = self._run("Q06")
        plan = candidate.terminal_protocol_trace[-1]["model_visible_claim_template_plan"]
        serialized = json.dumps(plan, ensure_ascii=False)
        self.assertIn("allowed_template_ids", serialized)
        for prose in [
            *REPORT_TITLE_TEMPLATES.values(),
            *INTERPRETATION_TEMPLATES.values(),
            *RECOMMENDATION_TEMPLATES.values(),
        ]:
            self.assertNotIn(prose, serialized)
        self.assertNotRegex(serialized, r"CALL-\d+")

    def test_q01_q10_offline_end_to_end(self) -> None:
        def transport_factory(_question_id: str):
            return OfflineDeepSeekProviderV2_3_4_2(
                ClaimTemplateLogicalClientV3_1(
                    CallIsolatedFrozenQuestionNativeToolMockClient()
                )
            )

        with tempfile.TemporaryDirectory() as temp:
            result = execute_validation_v3_1_full(
                api_key="offline-v3-1-runner-key",
                registry=FrozenH2MockRegistry(),
                transport_factory=transport_factory,
                authority=ToolRoutingAuthority("offline_injected_transport", "offline-not-real"),
                output_parent=Path(temp),
                run_id="claim_controller_v3_1_full_offline_test",
            )
            self.assertTrue(result.passed, result.summary)
            self.assertEqual(result.summary["question_ids_executed"], list(FULL_ORDER))
            self.assertEqual(result.summary["actual_response_attempts"], 27)
            self.assertEqual(result.summary["response_attempt_upper_bound"], FULL_CAP)
            self.assertEqual(
                result.summary["tool_selection_prompt_version"], COMBINED_PROMPT_VERSION
            )

    def test_repair_feedback_exposes_exact_local_literals_not_prose_templates(self) -> None:
        candidate, _ = self._run("Q01")
        plan = candidate.terminal_protocol_trace[-1]["model_visible_claim_template_plan"]
        from src.claim_level_report_controller_v3_1 import ClaimTemplatePlanEnvelopeV3_1
        from types import SimpleNamespace

        envelope = ClaimTemplatePlanEnvelopeV3_1.model_validate(plan)
        feedback = build_repair_feedback_v3_1(
            context=SimpleNamespace(model_visible=envelope),
            issues=[{"code": "required_literal_missing", "location": "claims[0]"}],
            repair_attempt=1,
        )
        first = feedback["authored_claim_contracts"][0]
        self.assertEqual(first["required_literals_exact"], ["sales_amount_gbp"])
        self.assertIn("do not translate", first["rule"])
        self.assertNotIn(
            next(iter(INTERPRETATION_TEMPLATES.values())),
            json.dumps(feedback, ensure_ascii=False),
        )


if __name__ == "__main__":
    unittest.main()
