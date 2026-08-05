from __future__ import annotations

import json
import unittest

from pydantic import ValidationError

from src.agent_decision_v2 import (
    BoundaryDecisionV2,
    ClarificationDecisionV2,
)
from src.agent_decision_v2_1 import parse_decision_v2_1
from src.analysis_recipes_v2_1 import (
    RECIPE_TOOL_SEQUENCE_V2_1,
    TOOL_CAPABILITIES_V2_1,
    AnalysisRecipeDecisionV2_1,
    RecipeV2_1Error,
    next_recipe_step,
    validate_explicit_question_constraints,
    validate_step_facts,
)
from src.fact_schema import (
    AnalysisScope,
    FactDimension,
    FactRecord,
)
from src.prompt_contract import load_report_boundary_prompts_v2_1
from src.report_semantics_v2_1 import (
    SemanticBlockPlanV2_1,
    SemanticReportPlanV2_1,
    SemanticSectionPlanV2_1,
    render_semantic_report_v2_1,
    validate_semantic_report_v2_1,
)


def fact(
    *,
    fact_id: str,
    call_id: str,
    source_tool: str,
    fact_type: str,
    metric: str,
    value: str,
    display_value: str,
    unit: str,
    dimensions: list[tuple[str, str]] | None = None,
    rank: int | None = None,
    period: str = "complete_months_only",
    start_date: str | None = None,
    end_date: str | None = None,
) -> FactRecord:
    return FactRecord(
        schema_version="1.5.6-h3-fact-v1",
        fact_id=fact_id,
        session_id="SESSION-v21",
        turn_id="TURN-001",
        call_id=call_id,
        fact_type=fact_type,
        metric=metric,
        value=value,
        display_value=display_value,
        unit=unit,
        analysis_scope=AnalysisScope(
            fact_layer="sales_fact",
            period=period,
            start_date=start_date,
            end_date=end_date,
            row_count=1,
        ),
        dimensions=[
            FactDimension(name=name, value=item_value)
            for name, item_value in (dimensions or [])
        ],
        rank=rank,
        source_tool=source_tool,
        source_result_path=(
            f"results/raw/test/TURN-001/{call_id}/result.json"
        ),
    )


def q06_facts() -> list[FactRecord]:
    return [
        fact(
            fact_id="FACT-001",
            call_id="CALL-001",
            source_tool="analyze_time_trend",
            fact_type="period_marker",
            metric="peak_period",
            value="2011-11",
            display_value="2011-11",
            unit="calendar_month",
            dimensions=[("month", "2011-11")],
            rank=1,
        ),
        fact(
            fact_id="FACT-036",
            call_id="CALL-001",
            source_tool="analyze_time_trend",
            fact_type="metric",
            metric="sales_amount",
            value="1503866.78",
            display_value="£1,503,866.78",
            unit="GBP",
            dimensions=[("month", "2011-11")],
            rank=1,
        ),
        fact(
            fact_id="FACT-040",
            call_id="CALL-002",
            source_tool="rank_products",
            fact_type="ranked_metric",
            metric="sales_amount",
            value="36905.40",
            display_value="£36,905.40",
            unit="GBP",
            dimensions=[
                ("stock_code", "DOT"),
                ("product_name", "DOTCOM POSTAGE"),
            ],
            rank=1,
            period="custom",
            start_date="2011-11-01",
            end_date="2011-11-30",
        ),
        fact(
            fact_id="FACT-043",
            call_id="CALL-002",
            source_tool="rank_products",
            fact_type="ranked_metric",
            metric="sales_amount",
            value="34478.40",
            display_value="£34,478.40",
            unit="GBP",
            dimensions=[
                ("stock_code", "23084"),
                ("product_name", "RABBIT NIGHT LIGHT"),
            ],
            rank=2,
            period="custom",
            start_date="2011-11-01",
            end_date="2011-11-30",
        ),
        fact(
            fact_id="FACT-046",
            call_id="CALL-002",
            source_tool="rank_products",
            fact_type="ranked_metric",
            metric="sales_amount",
            value="28955.54",
            display_value="£28,955.54",
            unit="GBP",
            dimensions=[
                ("stock_code", "22086"),
                ("product_name", "PAPER CHAIN KIT 50'S CHRISTMAS"),
            ],
            rank=3,
            period="custom",
            start_date="2011-11-01",
            end_date="2011-11-30",
        ),
    ]


def q06_decision() -> AnalysisRecipeDecisionV2_1:
    return AnalysisRecipeDecisionV2_1(
        decision_type="analysis_recipe",
        recipe_id="peak_month_product_ranking",
        period="complete_months_only",
        start_date=None,
        end_date=None,
        metric="sales_amount",
        top_n=3,
        excluded_country=None,
        profile_section=None,
    )


def q06_report_plan() -> SemanticReportPlanV2_1:
    peak_ids = ["FACT-001", "FACT-036"]
    rank_ids = ["FACT-040", "FACT-043", "FACT-046"]
    all_ids = [*peak_ids, *rank_ids]
    return SemanticReportPlanV2_1(
        schema_version="1.5.6-h3-semantic-report-plan-v2.1",
        session_id="SESSION-v21",
        turn_id="TURN-001",
        recipe_id="peak_month_product_ranking",
        sections=[
            SemanticSectionPlanV2_1(
                name="用户问题与分析口径",
                blocks=[
                    SemanticBlockPlanV2_1(
                        template_id="scope_from_facts",
                        fact_ids=peak_ids,
                    )
                ],
            ),
            SemanticSectionPlanV2_1(
                name="关键经营发现",
                blocks=[
                    SemanticBlockPlanV2_1(
                        template_id="peak_period_finding",
                        fact_ids=peak_ids,
                    ),
                    SemanticBlockPlanV2_1(
                        template_id="ranked_entities_finding",
                        fact_ids=rank_ids,
                    ),
                ],
            ),
            SemanticSectionPlanV2_1(
                name="工具证据与图表",
                blocks=[
                    SemanticBlockPlanV2_1(
                        template_id="tool_evidence_summary",
                        fact_ids=all_ids,
                    )
                ],
            ),
            SemanticSectionPlanV2_1(
                name="有限解释",
                blocks=[
                    SemanticBlockPlanV2_1(
                        template_id="descriptive_only",
                        fact_ids=all_ids,
                    )
                ],
            ),
            SemanticSectionPlanV2_1(
                name="经营建议",
                blocks=[
                    SemanticBlockPlanV2_1(
                        template_id="verify_with_additional_data",
                        fact_ids=[],
                    )
                ],
            ),
            SemanticSectionPlanV2_1(
                name="数据与分析限制",
                blocks=[
                    SemanticBlockPlanV2_1(
                        template_id="data_limitations",
                        fact_ids=[],
                    )
                ],
            ),
        ],
    )


class V2_1RecipeAndSemanticTests(unittest.TestCase):
    def test_prompt_versions_and_decision_types(self) -> None:
        prompts = load_report_boundary_prompts_v2_1()
        self.assertEqual(
            prompts.decision_gate.version,
            "1.5.6-h3-decision-gate-v2.1",
        )
        decision = parse_decision_v2_1(
            q06_decision().model_dump_json()
        )
        clarification = parse_decision_v2_1(
            json.dumps(
                {
                    "decision_type": "clarification",
                    "message": "请补充条件。",
                    "topics": ["time_range", "metric"],
                },
                ensure_ascii=False,
            )
        )
        boundary = parse_decision_v2_1(
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
        self.assertIsInstance(
            decision,
            AnalysisRecipeDecisionV2_1,
        )
        self.assertIsInstance(
            clarification,
            ClarificationDecisionV2,
        )
        self.assertIsInstance(boundary, BoundaryDecisionV2)

    def test_capability_registry_covers_all_frozen_tools(self) -> None:
        self.assertEqual(
            set(TOOL_CAPABILITIES_V2_1),
            {
                "get_data_profile",
                "get_sales_overview",
                "rank_products",
                "analyze_regions",
                "analyze_time_trend",
                "analyze_customers",
                "compare_segments",
            },
        )
        used_tools = {
            tool
            for sequence in RECIPE_TOOL_SEQUENCE_V2_1.values()
            for tool in sequence
        }
        self.assertEqual(used_tools, set(TOOL_CAPABILITIES_V2_1))

    def test_all_recipe_first_steps_expand_to_frozen_sequence(
        self,
    ) -> None:
        for recipe_id, sequence in RECIPE_TOOL_SEQUENCE_V2_1.items():
            decision = AnalysisRecipeDecisionV2_1(
                decision_type="analysis_recipe",
                recipe_id=recipe_id,
                period=(
                    "complete_months_only"
                    if recipe_id
                    in {
                        "peak_complete_month",
                        "peak_month_product_ranking",
                    }
                    else "all_data"
                ),
                start_date=None,
                end_date=None,
                metric="sales_amount",
                top_n=(
                    3
                    if recipe_id
                    in {
                        "product_ranking",
                        "region_ranking",
                        "peak_month_product_ranking",
                    }
                    else None
                ),
                excluded_country=(
                    "United Kingdom"
                    if recipe_id == "region_ranking"
                    else None
                ),
                profile_section=(
                    "all" if recipe_id == "data_profile" else None
                ),
            )

            step = next_recipe_step(
                decision,
                completed_tool_names=[],
                current_turn_facts=[],
            )

            self.assertEqual(step.tool_name, sequence[0])

    def test_q06_recipe_expands_to_peak_then_ranking(self) -> None:
        decision = q06_decision()
        validate_explicit_question_constraints(
            "先找出销售额最高的完整月份，再列出该月按销售额排名的前3个商品。",
            decision,
        )
        first = next_recipe_step(
            decision,
            completed_tool_names=[],
            current_turn_facts=[],
        )
        validate_step_facts(first, q06_facts()[:2])
        second = next_recipe_step(
            decision,
            completed_tool_names=["analyze_time_trend"],
            current_turn_facts=q06_facts()[:2],
        )

        self.assertEqual(first.tool_name, "analyze_time_trend")
        self.assertEqual(
            first.required_output_metrics,
            ("peak_period", "sales_amount"),
        )
        self.assertEqual(second.tool_name, "rank_products")
        self.assertEqual(
            second.arguments,
            {
                "period": "custom",
                "start_date": "2011-11-01",
                "end_date": "2011-11-30",
                "metric": "sales_amount",
                "top_n": 3,
            },
        )
        self.assertEqual(
            second.dependency_fact_ids,
            ("FACT-001",),
        )

    def test_q06_wrong_overview_prefix_and_missing_peak_are_rejected(
        self,
    ) -> None:
        with self.assertRaises(RecipeV2_1Error):
            next_recipe_step(
                q06_decision(),
                completed_tool_names=["get_sales_overview"],
                current_turn_facts=[],
            )
        with self.assertRaises(RecipeV2_1Error):
            next_recipe_step(
                q06_decision(),
                completed_tool_names=["analyze_time_trend"],
                current_turn_facts=[],
            )

    def test_explicit_q06_metric_top_n_and_recipe_conflicts_are_rejected(
        self,
    ) -> None:
        question = (
            "先找出销售额最高的完整月份，再列出该月"
            "按销售额排名的前3个商品。"
        )
        wrong_recipe = q06_decision().model_copy(
            update={"recipe_id": "product_ranking"}
        )
        wrong_metric = q06_decision().model_copy(
            update={"metric": "sales_quantity"}
        )
        wrong_top_n = q06_decision().model_copy(
            update={"top_n": 5}
        )

        for decision in (
            wrong_recipe,
            wrong_metric,
            wrong_top_n,
        ):
            with self.assertRaises(RecipeV2_1Error):
                validate_explicit_question_constraints(
                    question,
                    decision,
                )

    def test_semantic_templates_render_only_program_text(self) -> None:
        facts = q06_facts()
        plan = q06_report_plan()

        validation = validate_semantic_report_v2_1(plan, facts)
        markdown = render_semantic_report_v2_1(plan, facts)

        self.assertEqual(validation.status, "passed")
        self.assertIn("£1,503,866.78", markdown)
        self.assertIn("£36,905.40", markdown)
        self.assertIn("仅支持描述性比较", markdown)
        self.assertNotIn("显著份额", markdown)
        self.assertNotIn("驱动峰值", markdown)
        self.assertNotIn("narrative", plan.model_dump_json())

    def test_overview_fact_cannot_satisfy_peak_template(self) -> None:
        facts = q06_facts()
        overview = fact(
            fact_id="FACT-099",
            call_id="CALL-003",
            source_tool="get_sales_overview",
            fact_type="metric",
            metric="sales_amount",
            value="10004320.47",
            display_value="£10,004,320.47",
            unit="GBP",
        )
        plan = q06_report_plan()
        plan.sections[1].blocks[0].fact_ids = ["FACT-099"]

        validation = validate_semantic_report_v2_1(
            plan,
            [*facts, overview],
        )

        self.assertEqual(validation.status, "failed")
        self.assertIn(
            "fact_signature_mismatch",
            {issue.code for issue in validation.issues},
        )

    def test_free_narrative_field_is_rejected(self) -> None:
        payload = q06_report_plan().model_dump(mode="json")
        payload["sections"][1]["blocks"][0]["narrative"] = (
            "头部商品可能驱动峰值。"
        )

        with self.assertRaises(ValidationError):
            SemanticReportPlanV2_1.model_validate(payload)


if __name__ == "__main__":
    unittest.main()
