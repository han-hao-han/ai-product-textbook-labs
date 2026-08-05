from __future__ import annotations

import json
import unittest

from pydantic import ValidationError

from src.agent_decision_v2 import (
    AnalysisDecisionV2,
    BoundaryDecisionV2,
    ClarificationDecisionV2,
    DecisionProtocolError,
    parse_decision_v2,
)
from src.fact_schema import AnalysisScope, FactRecord
from src.prompt_contract import load_report_boundary_prompts_v2
from src.report_finalization_v2 import (
    ChartRequestV2,
    FinalReportResponseV2,
    ReportClaimPlanV2,
    ReportPlanV2,
    ReportSectionPlanV2,
    finalize_report_v2,
    render_finalized_report_v2,
    validate_report_plan_v2,
)
from src.report_validation import REPORT_SECTION_ORDER


KIND_BY_SECTION = {
    "用户问题与分析口径": "scope",
    "关键经营发现": "finding",
    "工具证据与图表": "evidence_note",
    "有限解释": "limited_interpretation",
    "经营建议": "recommendation",
    "数据与分析限制": "limitation",
}


def overview_facts() -> list[FactRecord]:
    """Minimal canonical FACT fixture without loading pandas."""

    return [
        FactRecord(
            schema_version="1.5.6-h3-fact-v1",
            fact_id="FACT-001",
            session_id="SESSION-test",
            turn_id="TURN-001",
            call_id="CALL-001",
            fact_type="metric",
            metric="sales_amount",
            value="4.47",
            display_value="£4.47",
            unit="GBP",
            analysis_scope=AnalysisScope(
                fact_layer="sales_fact",
                period="all_data",
                start_date=None,
                end_date=None,
                row_count=1,
            ),
            dimensions=[],
            rank=None,
            source_tool="get_sales_overview",
            source_result_path=(
                "results/raw/test/calls/CALL-001/result.json"
            ),
        )
    ]


def report_response_v2(fact_id: str) -> FinalReportResponseV2:
    sections = []
    for name in REPORT_SECTION_ORDER:
        kind = KIND_BY_SECTION[name]
        fact_ids = (
            []
            if kind in {"scope", "limitation"}
            else [fact_id]
        )
        narrative = {
            "scope": "分析采用冻结销售口径。",
            "finding": "程序证据显示当前指标具有明确结果。",
            "evidence_note": "工具证据支持本次经营发现。",
            "limited_interpretation": "该结果仅支持描述性观察。",
            "recommendation": "建议结合更多经营数据继续评估。",
            "limitation": "当前数据不能支持利润或因果判断。",
        }[kind]
        sections.append(
            ReportSectionPlanV2(
                name=name,
                claims=[
                    ReportClaimPlanV2(
                        claim_kind=kind,
                        narrative=narrative,
                        fact_ids=fact_ids,
                    )
                ],
            )
        )
    return FinalReportResponseV2(
        response_type="report",
        report=ReportPlanV2(
            schema_version="1.5.6-h3-report-plan-v2",
            session_id="SESSION-test",
            turn_id="TURN-001",
            title="销售概览与有限经营观察",
            sections=sections,
        ),
        chart_requests=[],
    )


class ReportFinalizationV2Tests(unittest.TestCase):
    def test_v2_prompts_are_versioned_and_numeric_boundary_is_explicit(
        self,
    ) -> None:
        prompts = load_report_boundary_prompts_v2()

        self.assertEqual(
            prompts.decision_gate.version,
            "1.5.6-h3-decision-gate-v2",
        )
        self.assertEqual(
            prompts.report_finalizer.version,
            "1.5.6-h3-report-finalizer-v2",
        )
        self.assertIn(
            "不得包含任何阿拉伯数字",
            prompts.report_finalizer.content,
        )

    def test_decision_gate_parses_all_three_outcomes(self) -> None:
        clarification = parse_decision_v2(
            json.dumps(
                {
                    "decision_type": "clarification",
                    "message": "请补充条件。",
                    "topics": ["time_range", "metric"],
                },
                ensure_ascii=False,
            )
        )
        boundary = parse_decision_v2(
            json.dumps(
                {
                    "decision_type": "boundary",
                    "message": "缺少成本字段。",
                    "missing_fields": ["cost", "profit"],
                    "supported_alternative": "销售额排名",
                },
                ensure_ascii=False,
            )
        )
        analysis = parse_decision_v2(
            json.dumps(
                {
                    "decision_type": "analysis",
                    "required_tools": [
                        "analyze_time_trend",
                        "rank_products",
                    ],
                },
                ensure_ascii=False,
            )
        )

        self.assertIsInstance(
            clarification,
            ClarificationDecisionV2,
        )
        self.assertIsInstance(boundary, BoundaryDecisionV2)
        self.assertIsInstance(analysis, AnalysisDecisionV2)

    def test_invalid_or_duplicate_tool_plan_is_rejected(self) -> None:
        with self.assertRaises(DecisionProtocolError):
            parse_decision_v2("not-json")
        with self.assertRaises(DecisionProtocolError):
            parse_decision_v2(
                json.dumps(
                    {
                        "decision_type": "analysis",
                        "required_tools": [
                            "rank_products",
                            "rank_products",
                        ],
                    }
                )
            )

    def test_model_narrative_with_any_digit_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            ReportClaimPlanV2(
                claim_kind="finding",
                narrative="峰值月份为二零一一年十一月，排名第1。",
                fact_ids=["FACT-001"],
            )

    def test_program_injects_canonical_fact_values(self) -> None:
        facts = overview_facts()
        response = report_response_v2(facts[0].fact_id)

        validation = validate_report_plan_v2(response, facts)
        finalized = finalize_report_v2(response, facts)
        markdown = render_finalized_report_v2(finalized)

        self.assertEqual(validation.status, "passed")
        self.assertNotIn("£4.47", response.model_dump_json())
        self.assertIn("£4.47", markdown)
        self.assertIn("[FACT-001]", markdown)
        self.assertIn("unit=GBP", markdown)

    def test_unknown_or_cross_turn_fact_is_rejected(self) -> None:
        facts = overview_facts()
        response = report_response_v2("FACT-999")

        validation = validate_report_plan_v2(response, facts)

        self.assertEqual(validation.status, "failed")
        self.assertIn(
            "unknown_fact",
            {issue.code for issue in validation.issues},
        )

    def test_chart_request_must_match_source_tool_call(self) -> None:
        facts = overview_facts()
        response = report_response_v2(facts[0].fact_id)
        response.chart_requests = [
            ChartRequestV2(
                call_id="CALL-001",
                chart_type="monthly_line",
                title="月度销售趋势",
            )
        ]

        validation = validate_report_plan_v2(response, facts)

        self.assertEqual(validation.status, "failed")
        self.assertIn(
            "invalid_chart_source",
            {issue.code for issue in validation.issues},
        )


if __name__ == "__main__":
    unittest.main()
