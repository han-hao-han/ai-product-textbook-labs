from __future__ import annotations

import unittest
from dataclasses import replace
from typing import Any

from src.fixed_question_validation import (
    load_frozen_questions,
    validate_fixed_question,
)
from src.mock_h2_registry import FrozenH2MockRegistry
from src.mock_native_tool_client_v2_1_revision import (
    FrozenQuestionNativeToolMockClient,
)
from src.native_tool_agent_v2_1_revision import (
    RetailNativeToolAgentV2_1Revision,
)
from src.report_validation import (
    REPORT_SECTION_ORDER,
    ReportClaim,
    ReportDraft,
    ReportSection,
    fact_reference,
    policy_reference,
    request_reference,
    validate_report,
)


def _flatten(value: Any, path: str = "") -> list[tuple[str, Any]]:
    if isinstance(value, dict):
        result: list[tuple[str, Any]] = []
        for key, item in value.items():
            child = f"{path}.{key}" if path else key
            result.extend(_flatten(item, child))
        return result
    if isinstance(value, list):
        result = []
        for index, item in enumerate(value):
            result.extend(_flatten(item, f"{path}[{index}]"))
        return result
    return [(path, value)]


def _run(question_id: str):
    question = load_frozen_questions()[question_id]["question"]
    return RetailNativeToolAgentV2_1Revision(
        client=FrozenQuestionNativeToolMockClient(),
        registry=FrozenH2MockRegistry(),
    ).run_turn(
        session_id="SESSION-six-boundary",
        turn_id=f"TURN-{int(question_id[1:]):03d}",
        question=question,
    )


def _complete_report(question_id: str, outcome):
    reference = load_frozen_questions()[question_id]["reference_answer"]
    parts = [str(value) for _, value in _flatten(reference)]
    if question_id == "Q06":
        parts.append("$request.top_n=3")
    evidence = [fact_reference(fact) for fact in outcome.facts]
    evidence.extend(request_reference(item) for item in outcome.request_records)
    evidence.extend(policy_reference(item) for item in outcome.policy_records)
    claims = {
        name: ReportClaim(
            statement="本节不新增数值结论。",
            evidence=[],
        )
        for name in REPORT_SECTION_ORDER
    }
    claims["关键经营发现"] = ReportClaim(
        statement="；".join(parts),
        evidence=evidence,
    )
    draft = ReportDraft(
        schema_version="1.5.6-h3-report-draft-v1",
        session_id=outcome.session_id,
        turn_id=outcome.turn_id,
        title=f"{question_id} 内容完整性固定夹具",
        sections=[
            ReportSection(name=name, claims=[claims[name]])
            for name in REPORT_SECTION_ORDER
        ],
    )
    validation = validate_report(
        draft,
        list(outcome.facts),
        list(outcome.request_records),
        list(outcome.policy_records),
    )
    if validation.status != "passed":
        raise AssertionError(
            [item.model_dump() for item in validation.issues]
        )
    return replace(
        outcome,
        report_draft=draft,
        report_validation=validation,
    )


class AcceptanceHarnessSixBoundaryImplementationTests(unittest.TestCase):
    def test_generic_mock_only_claims_protocol_and_dataflow(self) -> None:
        validations = {
            question_id: validate_fixed_question(
                question_id,
                _run(question_id),
            )
            for question_id in [f"Q{index:02d}" for index in range(1, 8)]
        }

        self.assertTrue(
            all(
                item.status == "protocol_and_dataflow_passed"
                for item in validations.values()
            )
        )
        self.assertTrue(
            all(item.protocol_mock_status == "passed" for item in validations.values())
        )
        self.assertTrue(
            all(
                item.report_content_acceptance_status == "failed"
                for item in validations.values()
            )
        )

    def test_complete_fact_request_policy_reports_cover_q01_q07(self) -> None:
        validations = {}
        for index in range(1, 8):
            question_id = f"Q{index:02d}"
            validations[question_id] = validate_fixed_question(
                question_id,
                _complete_report(question_id, _run(question_id)),
            )

        self.assertTrue(
            all(
                item.status
                == "passed_deterministic_pending_manual_review"
                for item in validations.values()
            ),
            {
                key: [issue.model_dump() for issue in item.issues]
                for key, item in validations.items()
                if item.issues
            },
        )
        self.assertTrue(
            all(
                manifest.covered
                for item in validations.values()
                for manifest in item.evidence_manifest
            )
        )
        self.assertEqual(
            {
                key: len(item.evidence_manifest)
                for key, item in validations.items()
            },
            {
                "Q01": 7,
                "Q02": 27,
                "Q03": 23,
                "Q04": 7,
                "Q05": 14,
                "Q06": 21,
                "Q07": 12,
            },
        )

    def test_rank_is_only_present_on_selected_metric(self) -> None:
        expected_cleared = {"Q02": 10, "Q03": 10, "Q06": 6}
        observed = {}
        for question_id in expected_cleared:
            outcome = _run(question_id)
            observed[question_id] = sum(
                fact.rank is None
                for call in outcome.tool_calls
                if call.tool_name in {"rank_products", "analyze_regions"}
                for fact in call.facts
                if fact.metric in {"sales_quantity", "order_count"}
            )
        self.assertEqual(observed, expected_cleared)

    def test_request_and_policy_references_are_program_owned(self) -> None:
        outcome = _run("Q07")
        self.assertTrue(outcome.policy_records)
        self.assertEqual(
            outcome.policy_records[0].code,
            "aggregate_customer_privacy",
        )
        q02 = _run("Q02")
        self.assertEqual(
            {
                (item.parameter_name, item.value, item.source)
                for item in q02.request_records
            },
            {
                ("top_n", "5", "validated_user_input"),
                ("metric", "sales_amount_gbp", "validated_user_input"),
            },
        )

    def test_q09_wrong_alternative_is_deterministically_rejected(self) -> None:
        outcome = _run("Q09")
        changed = replace(
            outcome,
            boundary=outcome.boundary.model_copy(
                update={"supported_alternative": "任意不受支持方案"}
            ),
        )

        validation = validate_fixed_question("Q09", changed)

        self.assertEqual(
            validation.status,
            "protocol_and_dataflow_passed",
        )
        self.assertEqual(
            validation.report_content_acceptance_status,
            "failed",
        )

    def test_q10_requires_two_codes_and_rejects_capability_promise(self) -> None:
        outcome = _run("Q10")
        changed = replace(
            outcome,
            boundary=outcome.boundary.model_copy(
                update={
                    "message": "可以直接预测并自动补货。",
                    "boundary_codes": ["forecasting_unsupported"],
                }
            ),
        )

        validation = validate_fixed_question("Q10", changed)
        paths = {item.path for item in validation.issues}

        self.assertEqual(
            validation.status,
            "protocol_and_dataflow_passed",
        )
        self.assertIn("boundary.boundary_codes", paths)
        self.assertIn("boundary.contradictory_capability_promise", paths)

    def test_q08_clarity_remains_manual_not_fake_automatic_failure(self) -> None:
        outcome = _run("Q08")
        changed = replace(
            outcome,
            clarification=outcome.clarification.model_copy(
                update={"message": "占位文本。"}
            ),
        )

        validation = validate_fixed_question("Q08", changed)

        self.assertEqual(
            validation.status,
            "passed_deterministic_pending_manual_review",
        )
        self.assertEqual(validation.manual_review_status, "pending")


if __name__ == "__main__":
    unittest.main()
