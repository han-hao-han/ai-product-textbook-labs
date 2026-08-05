from __future__ import annotations

import unittest

from src.fact_builder import FactBuildContext, FactBuilder
from src.evidence_provenance import PolicyRecord, RequestRecord
from src.report_validation import (
    REPORT_SECTION_ORDER,
    ReportClaim,
    ReportDraft,
    ReportSection,
    fact_reference,
    policy_reference,
    request_reference,
    render_validated_report,
    validate_report,
)
from src.retail_cleaning import build_retail_data_layers
from src.retail_tools import RetailToolService
from src.tool_registry import RetailToolRegistry
from tests.test_retail_cleaning import sample_frame


def overview_facts() -> list:
    layers = build_retail_data_layers(sample_frame())
    registry = RetailToolRegistry(RetailToolService(layers))
    result = registry.execute(
        "get_sales_overview",
        {
            "period": "all_data",
            "start_date": None,
            "end_date": None,
            "include_incomplete_period_warning": True,
        },
    )
    return FactBuilder().build(
        result,
        FactBuildContext(
            session_id="SESSION-test",
            turn_id="TURN-001",
            call_id="CALL-001",
            source_result_path=(
                "results/raw/test/calls/CALL-001/result.json"
            ),
        ),
    )


def report_for_fact(fact, statement: str | None = None) -> ReportDraft:
    claims = {
        name: ReportClaim(
            statement="本节未引入新的数值结论。",
            evidence=[],
        )
        for name in REPORT_SECTION_ORDER
    }
    claims["关键经营发现"] = ReportClaim(
        statement=statement
        or f"正常销售额为{fact.display_value}。",
        evidence=[fact_reference(fact)],
    )
    return ReportDraft(
        schema_version="1.5.6-h3-report-draft-v1",
        session_id="SESSION-test",
        turn_id="TURN-001",
        title="经营分析报告",
        sections=[
            ReportSection(name=name, claims=[claims[name]])
            for name in REPORT_SECTION_ORDER
        ],
    )


class ReportValidationTests(unittest.TestCase):
    def test_request_and_policy_references_validate_and_render(self) -> None:
        facts = overview_facts()
        request = RequestRecord(
            request_id="REQUEST-001",
            session_id="SESSION-test",
            turn_id="TURN-001",
            parameter_name="top_n",
            value="5",
            source="validated_user_input",
        )
        policy = PolicyRecord(
            policy_id="POLICY-002",
            code="incomplete_2011_12",
            message="2011-12是不完整期间",
        )
        draft = report_for_fact(facts[0])
        draft.sections[0].claims[0] = ReportClaim(
            statement="用户要求前5项；2011-12是不完整期间。",
            evidence=[
                request_reference(request),
                policy_reference(policy),
            ],
        )

        validation = validate_report(
            draft,
            facts,
            [request],
            [policy],
        )
        markdown = render_validated_report(
            draft,
            facts,
            [request],
            [policy],
        )

        self.assertEqual(validation.status, "passed")
        self.assertEqual(validation.referenced_request_ids, ["REQUEST-001"])
        self.assertEqual(validation.referenced_policy_ids, ["POLICY-002"])
        self.assertIn("[REQUEST-001]", markdown)
        self.assertIn("[POLICY-002]", markdown)

    def test_unknown_request_and_policy_references_are_rejected(self) -> None:
        facts = overview_facts()
        request = RequestRecord(
            request_id="REQUEST-001",
            session_id="SESSION-test",
            turn_id="TURN-001",
            parameter_name="top_n",
            value="5",
            source="validated_user_input",
        )
        policy = PolicyRecord(
            policy_id="POLICY-002",
            code="incomplete_2011_12",
            message="2011-12是不完整期间",
        )
        draft = report_for_fact(facts[0])
        draft.sections[0].claims[0] = ReportClaim(
            statement="用户要求前5项；2011-12是不完整期间。",
            evidence=[
                request_reference(request),
                policy_reference(policy),
            ],
        )

        validation = validate_report(draft, facts)

        self.assertEqual(validation.status, "failed")
        self.assertEqual(
            {item.code for item in validation.issues},
            {"unknown_request", "unknown_policy"},
        )

    def test_valid_report_passes_and_program_adds_citation(self) -> None:
        facts = overview_facts()
        draft = report_for_fact(facts[0])

        validation = validate_report(draft, facts)
        markdown = render_validated_report(draft, facts)

        self.assertEqual(validation.status, "passed")
        self.assertIn("[FACT-001]", markdown)
        self.assertIn("£4.47", markdown)

    def test_changed_value_and_unit_are_rejected(self) -> None:
        facts = overview_facts()
        reference = fact_reference(facts[0]).model_copy(
            update={"value": "999.99", "unit": "items"}
        )
        draft = report_for_fact(facts[0])
        draft.sections[1].claims[0].evidence = [reference]

        validation = validate_report(draft, facts)
        codes = {issue.code for issue in validation.issues}

        self.assertEqual(validation.status, "failed")
        self.assertIn("fact_value_mismatch", codes)
        self.assertIn("fact_unit_mismatch", codes)

    def test_unreferenced_number_is_rejected(self) -> None:
        facts = overview_facts()
        draft = report_for_fact(
            facts[0],
            statement="正常销售额为£999.99。",
        )

        validation = validate_report(draft, facts)

        self.assertIn(
            "untraceable_numeric_token",
            {issue.code for issue in validation.issues},
        )

    def test_historical_turn_fact_is_rejected(self) -> None:
        facts = overview_facts()
        draft = report_for_fact(facts[0])
        draft.turn_id = "TURN-002"

        validation = validate_report(draft, facts)

        self.assertIn(
            "cross_turn_fact",
            {issue.code for issue in validation.issues},
        )

    def test_chinese_month_matches_same_month_fact_scope(self) -> None:
        facts = overview_facts()
        fact = facts[0].model_copy(
            update={
                "analysis_scope": facts[0].analysis_scope.model_copy(
                    update={
                        "period": "custom",
                        "start_date": "2011-11-01",
                        "end_date": "2011-11-30",
                    }
                )
            }
        )
        draft = report_for_fact(
            fact,
            statement=f"2011年11月正常销售额为{fact.display_value}。",
        )

        validation = validate_report(draft, [fact])

        self.assertEqual(validation.status, "passed")
        self.assertNotIn(
            "untraceable_numeric_token",
            {issue.code for issue in validation.issues},
        )

    def test_cross_month_scope_does_not_support_one_month_claim(self) -> None:
        facts = overview_facts()
        fact = facts[0].model_copy(
            update={
                "analysis_scope": facts[0].analysis_scope.model_copy(
                    update={
                        "period": "custom",
                        "start_date": "2011-11-15",
                        "end_date": "2011-12-15",
                    }
                )
            }
        )
        draft = report_for_fact(
            fact,
            statement=f"2011年11月正常销售额为{fact.display_value}。",
        )

        validation = validate_report(draft, [fact])

        self.assertIn(
            "untraceable_numeric_token",
            {issue.code for issue in validation.issues},
        )

    def test_plain_semantic_classifications_route_to_manual_review(
        self,
    ) -> None:
        facts = overview_facts()
        draft = report_for_fact(facts[0])
        draft.sections[3].claims[0] = ReportClaim(
            statement=(
                "该结果显著高于其他期间，属于高客单价和走量型商品。"
            ),
            evidence=[fact_reference(facts[0])],
        )

        validation = validate_report(draft, facts)
        codes = {issue.code for issue in validation.issues}

        self.assertEqual(validation.status, "passed")
        self.assertEqual(codes, set())
        self.assertEqual(
            {item.code for item in validation.manual_review_flags},
            {
                "plain_significant_wording",
                "unfrozen_average_value_classification",
                "product_business_classification",
            },
        )

    def test_explicit_statistics_and_unsupported_aov_number_fail(self) -> None:
        facts = overview_facts()
        draft = report_for_fact(facts[0])
        draft.sections[3].claims[0] = ReportClaim(
            statement="该结果统计显著，客单价为999.99。",
            evidence=[fact_reference(facts[0])],
        )

        validation = validate_report(draft, facts)
        codes = {issue.code for issue in validation.issues}

        self.assertEqual(validation.status, "failed")
        self.assertIn("unsupported_significance_claim", codes)
        self.assertIn("unsupported_average_value_claim", codes)

    def test_manual_flags_do_not_fail_or_rewrite_report(self) -> None:
        facts = overview_facts()
        draft = report_for_fact(facts[0])
        explanation = "该结果可能处于销售旺季。"
        recommendation = "建议提前备货并优化物流。"
        draft.sections[3].claims[0] = ReportClaim(
            statement=explanation,
            evidence=[fact_reference(facts[0])],
        )
        draft.sections[4].claims[0] = ReportClaim(
            statement=recommendation,
            evidence=[fact_reference(facts[0])],
        )

        validation = validate_report(draft, facts)

        self.assertEqual(validation.status, "passed")
        self.assertEqual(
            {flag.code for flag in validation.manual_review_flags},
            {
                "seasonality_interpretation",
                "inventory_action",
                "pricing_or_logistics_action",
            },
        )
        self.assertEqual(
            draft.sections[3].claims[0].statement,
            explanation,
        )
        self.assertEqual(
            draft.sections[4].claims[0].statement,
            recommendation,
        )


if __name__ == "__main__":
    unittest.main()
