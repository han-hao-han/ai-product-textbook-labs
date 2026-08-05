from __future__ import annotations

import unittest
from copy import deepcopy

from src.fact_schema import AnalysisScope, FactDimension, FactRecord
from src.report_evidence_semantic_boundary_v2_2_2 import (
    REAL_EVIDENCE_PATH,
    ReportEvidenceSemanticBoundaryError,
    allowed_canonical_tokens,
    canonical_numeric_tokens,
    collect_manual_review_flags,
    load_report_evidence_semantic_contract,
    replay_v2_2_1_real_report,
    validate_deterministic_semantics,
    validate_v2_2_2_contract,
)
from src.report_validation import (
    REPORT_SECTION_ORDER,
    ReportClaim,
    ReportDraft,
    ReportSection,
    fact_reference,
)


def make_fact(
    *,
    fact_id: str,
    metric: str,
    value: str,
    unit: str,
    rank: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    dimensions: list[FactDimension] | None = None,
) -> FactRecord:
    return FactRecord(
        schema_version="1.5.6-h3-fact-v1",
        fact_id=fact_id,
        session_id="SESSION-v222",
        turn_id="TURN-006",
        call_id="CALL-001",
        fact_type="ranked_metric" if rank else "metric",
        metric=metric,
        value=value,
        display_value=value,
        unit=unit,
        analysis_scope=AnalysisScope(
            fact_layer="sales_fact",
            period="custom" if start_date else "complete_months_only",
            start_date=start_date,
            end_date=end_date,
            row_count=10,
        ),
        dimensions=dimensions or [],
        rank=rank,
        source_tool="test_tool",
        source_result_path="results/raw/test/result.json",
    )


def make_draft(
    *,
    explanation: str,
    recommendation: str,
    evidence: list,
) -> ReportDraft:
    statements = {
        "有限解释": explanation,
        "经营建议": recommendation,
    }
    return ReportDraft(
        schema_version="1.5.6-h3-report-draft-v1",
        session_id="SESSION-v222",
        turn_id="TURN-006",
        title="测试报告",
        sections=[
            ReportSection(
                name=name,
                claims=[
                    ReportClaim(
                        statement=statements.get(name, "无新增数值。"),
                        evidence=evidence if name in statements else [],
                    )
                ],
            )
            for name in REPORT_SECTION_ORDER
        ],
    )


class ReportEvidenceSemanticBoundaryV2_2_2Tests(unittest.TestCase):
    def test_calendar_expressions_have_one_canonical_token(self) -> None:
        self.assertEqual(
            canonical_numeric_tokens("2011年11月"),
            {"2011-11"},
        )
        self.assertEqual(
            canonical_numeric_tokens("2011年11月1日"),
            {"2011-11-01"},
        )
        self.assertEqual(
            canonical_numeric_tokens("2011-11"),
            {"2011-11"},
        )

    def test_same_month_scope_allows_month_but_cross_month_does_not(self) -> None:
        same = make_fact(
            fact_id="FACT-001",
            metric="sales_amount",
            value="100",
            unit="GBP",
            start_date="2011-11-01",
            end_date="2011-11-30",
        )
        cross = make_fact(
            fact_id="FACT-002",
            metric="sales_amount",
            value="200",
            unit="GBP",
            start_date="2011-11-15",
            end_date="2011-12-15",
        )
        self.assertIn("2011-11", allowed_canonical_tokens([same]))
        self.assertNotIn("2011-11", allowed_canonical_tokens([cross]))

    def test_deterministic_semantic_rules_require_specific_fact_capability(
        self,
    ) -> None:
        quantity = make_fact(
            fact_id="FACT-010",
            metric="sales_quantity",
            value="100",
            unit="items",
        )
        orders = make_fact(
            fact_id="FACT-011",
            metric="order_count",
            value="20",
            unit="orders",
        )
        evidence = [fact_reference(quantity), fact_reference(orders)]
        draft = make_draft(
            explanation=(
                "结果显著高于其他月份，销量与订单数也最高，"
                "属于高客单价和走量型商品。"
            ),
            recommendation="建议人工复核。",
            evidence=evidence,
        )
        codes = {
            issue.code
            for issue in validate_deterministic_semantics(
                draft,
                [quantity, orders],
            )
        }
        self.assertEqual(
            codes,
            {
                "unsupported_quantity_superlative",
                "unsupported_order_superlative",
            },
        )

    def test_manual_flags_are_separate_from_hard_semantic_issues(self) -> None:
        fact = make_fact(
            fact_id="FACT-020",
            metric="sales_amount",
            value="100",
            unit="GBP",
        )
        evidence = [fact_reference(fact)]
        draft = make_draft(
            explanation="该结果表明可能存在旺季特征。",
            recommendation="建议提前备货并优化物流与定价策略。",
            evidence=evidence,
        )
        hard = validate_deterministic_semantics(draft, [fact])
        flags = collect_manual_review_flags(draft)
        self.assertEqual(hard, ())
        self.assertEqual(
            {flag.code for flag in flags},
            {
                "seasonality_interpretation",
                "inventory_action",
                "pricing_or_logistics_action",
                "causal_or_effect_claim",
            },
        )

    def test_contract_rejects_cross_claim_borrowing_or_auto_repair(self) -> None:
        contract = validate_v2_2_2_contract()
        self.assertEqual(
            contract["status"],
            "frozen_by_user_formal_validator_integrated_offline_validated",
        )
        self.assertEqual(
            contract["user_freeze"]["status"],
            "frozen_by_user",
        )
        self.assertTrue(
            contract["user_freeze"][
                "freeze_does_not_authorize_real_calls"
            ]
        )
        self.assertEqual(
            contract["formal_validator_integration"][
                "formal_validation_status"
            ],
            "failed",
        )
        self.assertEqual(
            contract["formal_validator_integration"][
                "canonical_numeric_issue_count"
            ],
            1,
        )
        mock_regression = contract["formal_validator_integration"][
            "q01_q10_mock_regression"
        ]
        self.assertEqual(mock_regression["questions_passed"], 10)
        self.assertEqual(mock_regression["questions_total"], 10)
        self.assertFalse(mock_regression["network_used"])
        borrowing = deepcopy(load_report_evidence_semantic_contract())
        borrowing["claim_evidence_candidate"][
            "cross_claim_fact_borrowing_allowed"
        ] = True
        with self.assertRaises(ReportEvidenceSemanticBoundaryError):
            validate_v2_2_2_contract(borrowing)

        repair = deepcopy(load_report_evidence_semantic_contract())
        repair["scope"]["automatic_report_repair_allowed"] = True
        with self.assertRaises(ReportEvidenceSemanticBoundaryError):
            validate_v2_2_2_contract(repair)

    @unittest.skipUnless(
        REAL_EVIDENCE_PATH.exists(),
        "local real Q06 evidence is intentionally not repository data",
    )
    def test_saved_real_response_replay_preserves_missing_claim_evidence(
        self,
    ) -> None:
        replay = replay_v2_2_1_real_report()
        self.assertEqual(len(replay.current_numeric_issues), 16)
        self.assertEqual(len(replay.canonical_numeric_issues), 1)
        self.assertEqual(
            replay.canonical_numeric_issues[0].token_or_phrase,
            "3",
        )
        self.assertTrue(replay.source_response_unchanged)
        self.assertGreater(len(replay.deterministic_semantic_issues), 0)
        self.assertGreater(len(replay.manual_review_flags), 0)
        self.assertEqual(replay.formal_validation_status, "failed")
        self.assertEqual(len(replay.formal_validation_issues), 6)
        self.assertEqual(
            {
                issue.code
                for issue in replay.formal_validation_issues
            },
            {
                "untraceable_numeric_token",
                "unsupported_sales_amount_superlative",
                "unsupported_quantity_superlative",
                "unsupported_order_superlative",
                "unsupported_average_value_claim",
            },
        )
        self.assertEqual(len(replay.formal_manual_review_flags), 13)


if __name__ == "__main__":
    unittest.main()
