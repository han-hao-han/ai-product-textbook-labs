from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from src.deepseek_client import ChatCompletionResult
from src.fixed_question_validation import (
    load_frozen_questions,
    validate_fixed_question,
)
from src.mock_h2_registry import FrozenH2MockRegistry
from src.mock_native_tool_client_v2_1_revision import _tool_payloads
from src.native_tool_agent_v2_1_revision import (
    RetailNativeToolAgentV2_1Revision,
)
from src.native_tool_transport_mock_v2_1_revision import (
    OfflineNativeToolTransportV2_1Revision,
)
from src.q01_q10_batch_a_offline_mock import (
    BATCH_A_QUESTION_IDS,
    BatchAEvidenceCompleteMockClient,
)
from src.q01_q10_batch_a_safe_runner import (
    BATCH_A_OFFLINE_CONFIRMATION,
    execute_batch_a_validation,
    validate_offline_execution_request,
)
from src.report_validation import ReportDraft
from src.run_record import TurnRunRecord


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAVED_CASE_PATH = (
    PROJECT_ROOT
    / "results"
    / "raw"
    / "q01_q10_batch_a_flash_20260803T195956_363133+0800"
    / "Q02.json"
)
NOT_EVALUATED = (
    "not_evaluated_due_to_upstream_report_validation_failure"
)
ROOT_CODES = [
    "untraceable_numeric_token",
    "unsupported_average_value_claim",
    "unsupported_average_value_claim",
]


def _saved_report_payload() -> dict:
    case = json.loads(SAVED_CASE_PATH.read_text(encoding="utf-8"))
    content = case["outcome"]["raw_responses"][1]["choices"][0][
        "message"
    ]["content"]
    return json.loads(content)


class SavedQ02FailureClient(BatchAEvidenceCompleteMockClient):
    def complete_strict_tools(self, **kwargs):
        messages = kwargs["messages"]
        user_question = next(
            item["content"]
            for item in messages
            if item.get("role") == "user"
        )
        q02 = load_frozen_questions()["Q02"]["question"]
        payloads = _tool_payloads(messages)
        if user_question == q02 and len(payloads) == 1:
            payload = _saved_report_payload()
            first_fact = payloads[0]["facts"][0]
            payload["report"]["session_id"] = first_fact["session_id"]
            payload["report"]["turn_id"] = first_fact["turn_id"]
            return ChatCompletionResult(
                finish_reason="stop",
                content=json.dumps(payload, ensure_ascii=False),
                tool_calls=(),
                raw_response={
                    "offline": True,
                    "source": "saved_q02_flash_report",
                },
                usage=None,
            )
        return super().complete_strict_tools(**kwargs)


def _run_saved_q02():
    return RetailNativeToolAgentV2_1Revision(
        client=SavedQ02FailureClient(),
        registry=FrozenH2MockRegistry(),
        terminal_lock_question_ids=BATCH_A_QUESTION_IDS,
        terminal_json_question_ids=BATCH_A_QUESTION_IDS,
    ).run_turn(
        session_id="SESSION-q02-saved-response-regression",
        turn_id="TURN-002",
        question=load_frozen_questions()["Q02"]["question"],
        result_root="results/raw/q02_saved_response_regression",
    )


class Q02FailureHarnessRevisionImplementationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.outcome = _run_saved_q02()
        cls.validation = validate_fixed_question("Q02", cls.outcome)

    def test_rejected_report_is_retained_but_never_publishable(self) -> None:
        outcome = self.outcome
        self.assertEqual(outcome.status, "failed")
        self.assertEqual(outcome.error_stage, "report_validation")
        self.assertIsNone(outcome.report_draft)
        self.assertIsNone(outcome.report_markdown)
        self.assertIsNone(outcome.report_validation)
        rejected = outcome.rejected_report_evidence
        self.assertIsNotNone(rejected)
        self.assertFalse(rejected.publishable)
        self.assertFalse(rejected.charts_materialized)
        self.assertEqual(len(rejected.chart_requests), 1)
        self.assertEqual(len(rejected.request_records), 2)
        self.assertEqual(
            [item.code for item in rejected.report_validation.issues],
            ROOT_CODES,
        )

    def test_harness_short_circuits_formal_downstream_checks(self) -> None:
        validation = self.validation
        self.assertEqual(validation.status, "failed")
        self.assertEqual(
            validation.report_content_acceptance_status,
            NOT_EVALUATED,
        )
        self.assertEqual(len(validation.evidence_manifest), 27)
        self.assertTrue(all(item.covered for item in validation.evidence_manifest))
        self.assertFalse(
            any(
                item.path.startswith("report_completeness.")
                for item in validation.issues
            )
        )
        self.assertEqual(
            [item.path for item in validation.issues],
            ["outcome.status", "report_validation.status"],
        )

    def test_request_alias_requires_exact_program_request_reference(self) -> None:
        rejected = self.outcome.rejected_report_evidence
        without_requests = replace(
            self.outcome,
            rejected_report_evidence=replace(
                rejected,
                request_records=(),
            ),
        )
        validation = validate_fixed_question("Q02", without_requests)
        metric = next(
            item for item in validation.evidence_manifest
            if item.path == "metric"
        )
        self.assertFalse(metric.covered)

        report_payload = rejected.report_draft.model_dump(mode="json")
        for section in report_payload["sections"]:
            for claim in section["claims"]:
                if any(
                    item.get("evidence_type") == "REQUEST"
                    and item.get("parameter_name") == "metric"
                    for item in claim["evidence"]
                ):
                    claim["statement"] = claim["statement"].replace(
                        "销售额", "指标"
                    )
        without_alias = replace(
            self.outcome,
            rejected_report_evidence=replace(
                rejected,
                report_draft=ReportDraft.model_validate(report_payload),
            ),
        )
        validation = validate_fixed_question("Q02", without_alias)
        metric = next(
            item for item in validation.evidence_manifest
            if item.path == "metric"
        )
        self.assertFalse(metric.covered)

    def test_rejected_report_does_not_enter_current_run_record_schema(self) -> None:
        self.assertNotIn(
            "rejected_report_evidence",
            TurnRunRecord.model_fields,
        )

    def test_batch_runner_reports_root_and_suppresses_cascades(self) -> None:
        transport = OfflineNativeToolTransportV2_1Revision(
            SavedQ02FailureClient(),
            expected_model="deepseek-v4-flash",
            terminal_question_ids=BATCH_A_QUESTION_IDS,
            terminal_json_question_ids=BATCH_A_QUESTION_IDS,
        )
        with tempfile.TemporaryDirectory(
            dir=PROJECT_ROOT / "results" / "raw"
        ) as temporary:
            result = execute_batch_a_validation(
                api_key="offline-q02-revision-implementation-secret",
                registry=FrozenH2MockRegistry(),
                transport=transport,
                authority=validate_offline_execution_request(
                    confirmation=BATCH_A_OFFLINE_CONFIRMATION
                ),
                output_parent=Path(temporary),
                run_id="q02-rejected-report-runner-regression",
            )
            self.assertFalse(result.passed)
            self.assertEqual(
                result.summary["question_ids_executed"], ["Q02"]
            )
            self.assertEqual(
                result.summary["question_ids_not_executed"],
                ["Q06", "Q08", "Q09", "Q10"],
            )
            self.assertEqual(
                result.summary["stop_reason"],
                "report_validation_failed",
            )
            self.assertEqual(
                result.summary["primary_stop_stage"],
                "report_validation",
            )
            self.assertEqual(
                result.summary["primary_stop_codes"], ROOT_CODES
            )
            self.assertEqual(
                result.summary["not_evaluated_checks"],
                ["report_completeness", "chart_acceptance"],
            )
            case = result.cases[0]
            self.assertNotIn(
                "q02_chart_count_mismatch",
                case["program_failures"],
            )
            self.assertEqual(
                case["evaluation_states"]["report_completeness"],
                NOT_EVALUATED,
            )
            self.assertEqual(
                case["evaluation_states"]["chart_acceptance"],
                NOT_EVALUATED,
            )
            saved = json.loads(
                (result.output_dir / "Q02.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertIsNone(saved["outcome"]["report_draft"])
            self.assertIsNone(saved["outcome"]["report_validation"])
            self.assertFalse(
                saved["outcome"]["rejected_report_evidence"][
                    "publishable"
                ]
            )


if __name__ == "__main__":
    unittest.main()
