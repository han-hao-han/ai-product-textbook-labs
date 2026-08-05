from __future__ import annotations

import unittest
from copy import deepcopy

from src.q06_report_revision_feedback_boundary_v2_2_3 import (
    REAL_EVIDENCE_PATH,
    Q06ReportRevisionFeedbackBoundaryError,
    build_report_revision_feedback,
    load_q06_report_revision_feedback_contract,
    replay_saved_q06_feedback_design,
    validate_q06_report_revision_feedback_contract,
)
from src.report_validation import (
    ReportIssue,
    ReportValidationResult,
)


def failed_validation(code: str) -> ReportValidationResult:
    return ReportValidationResult(
        schema_version="1.5.6-h3-report-validation-v1",
        status="failed",
        issues=[
            ReportIssue(
                code=code,
                location="sections[0].claims[0]",
                message="数值或期间没有FACT证据：3。",
            )
        ],
        referenced_fact_ids=["FACT-001"],
        deterministic_checks=[],
        manual_review_flags=[
            ReportIssue(
                code="seasonality_interpretation",
                location="sections[3].claims[0]",
                message="必须由人工判断。",
            )
        ],
        manual_review_required_sections=["有限解释", "经营建议"],
    )


class Q06ReportRevisionFeedbackBoundaryV2_2_3Tests(unittest.TestCase):
    def test_contract_preserves_offline_zero_authority_boundary(self) -> None:
        contract = validate_q06_report_revision_feedback_contract()

        self.assertEqual(
            contract["status"],
            "paused_by_user_pending_q01_q10_acceptance_harness_audit",
        )
        self.assertFalse(contract["scope"]["real_model_calls_allowed"])
        self.assertFalse(contract["candidate_revision_protocol"]["active"])
        self.assertEqual(
            contract["user_pause"]["status"],
            "paused_by_user",
        )
        self.assertFalse(
            contract["user_pause"]["real_model_calls_allowed"]
        )
        self.assertEqual(
            contract["candidate_revision_protocol"][
                "maximum_report_revision_responses"
            ],
            1,
        )
        self.assertEqual(
            contract["candidate_revision_protocol"][
                "automatic_retry_count"
            ],
            0,
        )
        self.assertEqual(
            contract["offline_validation"]["negative_probes_passed"],
            9,
        )
        self.assertEqual(
            contract["offline_validation"]["q01_q10_mock_regression"][
                "questions_passed"
            ],
            10,
        )

    def test_feedback_contains_only_whitelisted_deterministic_issue(
        self,
    ) -> None:
        feedback = build_report_revision_feedback(
            failed_validation("untraceable_numeric_token")
        )
        payload = feedback.model_dump(mode="json")

        self.assertEqual(len(payload["issues"]), 1)
        self.assertEqual(payload["issues"][0]["unsupported_expression"], "3")
        self.assertNotIn("manual_review_flags", payload)
        self.assertNotIn("fact_ids", payload)
        self.assertNotIn("replacement_statement", payload)

    def test_hard_stop_issue_cannot_be_converted_to_revision_feedback(
        self,
    ) -> None:
        with self.assertRaises(Q06ReportRevisionFeedbackBoundaryError):
            build_report_revision_feedback(
                failed_validation("cross_turn_fact")
            )

    def test_contract_rejects_retry_authority_or_program_fact_selection(
        self,
    ) -> None:
        retry = deepcopy(load_q06_report_revision_feedback_contract())
        retry["candidate_revision_protocol"]["automatic_retry_count"] = 1
        with self.assertRaises(Q06ReportRevisionFeedbackBoundaryError):
            validate_q06_report_revision_feedback_contract(retry)

        authority = deepcopy(load_q06_report_revision_feedback_contract())
        authority["scope"]["real_model_calls_allowed"] = True
        with self.assertRaises(Q06ReportRevisionFeedbackBoundaryError):
            validate_q06_report_revision_feedback_contract(authority)

        fact_selection = deepcopy(
            load_q06_report_revision_feedback_contract()
        )
        fact_selection["deterministic_feedback_candidate"][
            "exclude_fields"
        ].remove("candidate_fact_ids_selected_by_program")
        with self.assertRaises(Q06ReportRevisionFeedbackBoundaryError):
            validate_q06_report_revision_feedback_contract(fact_selection)

    @unittest.skipUnless(
        REAL_EVIDENCE_PATH.exists(),
        "local real Q06 evidence is intentionally not repository data",
    )
    def test_saved_q06_stays_paused_when_new_hard_rule_is_not_whitelisted(
        self,
    ) -> None:
        before = REAL_EVIDENCE_PATH.read_bytes()
        with self.assertRaises(Q06ReportRevisionFeedbackBoundaryError):
            replay_saved_q06_feedback_design()
        self.assertEqual(REAL_EVIDENCE_PATH.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
