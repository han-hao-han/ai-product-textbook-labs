"""Offline V2.1 validation using saved real FACT records."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.analysis_recipes_v2_1 import (  # noqa: E402
    AnalysisRecipeDecisionV2_1,
    RecipeV2_1Error,
    next_recipe_step,
    validate_explicit_question_constraints,
    validate_step_facts,
)
from src.fact_schema import FactRecord  # noqa: E402
from src.report_semantics_v2_1 import (  # noqa: E402
    SemanticBlockPlanV2_1,
    SemanticReportPlanV2_1,
    SemanticSectionPlanV2_1,
    render_semantic_report_v2_1,
    validate_semantic_report_v2_1,
)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _decision() -> AnalysisRecipeDecisionV2_1:
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


def _q06_facts(facts: list[FactRecord]) -> list[FactRecord]:
    return [
        fact
        for fact in facts
        if (
            (
                fact.source_tool == "analyze_time_trend"
                and (
                    fact.metric == "peak_period"
                    or (
                        fact.metric == "sales_amount"
                        and fact.rank == 1
                    )
                )
            )
            or (
                fact.source_tool == "rank_products"
                and fact.metric == "sales_amount"
                and fact.rank is not None
            )
        )
    ]


def _plan(
    *,
    session_id: str,
    turn_id: str,
    facts: list[FactRecord],
) -> SemanticReportPlanV2_1:
    peak_ids = [
        fact.fact_id
        for fact in facts
        if fact.source_tool == "analyze_time_trend"
    ]
    rank_ids = [
        fact.fact_id
        for fact in sorted(
            (
                item
                for item in facts
                if item.source_tool == "rank_products"
            ),
            key=lambda item: item.rank or 0,
        )
    ]
    all_ids = [*peak_ids, *rank_ids]
    return SemanticReportPlanV2_1(
        schema_version="1.5.6-h3-semantic-report-plan-v2.1",
        session_id=session_id,
        turn_id=turn_id,
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


def _turn(
    record: dict[str, Any],
    turn_id: str,
) -> dict[str, Any]:
    return next(
        item for item in record["turns"] if item["turn_id"] == turn_id
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--correct-session-record", type=Path, required=True)
    parser.add_argument("--correct-turn-id", default="TURN-001")
    parser.add_argument("--failed-v2-outcome", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    record = json.loads(
        args.correct_session_record.read_text(encoding="utf-8")
    )
    correct_turn = _turn(record, args.correct_turn_id)
    all_correct_facts = [
        FactRecord.model_validate(item)
        for item in correct_turn["facts"]
    ]
    facts = _q06_facts(all_correct_facts)
    decision = _decision()
    validate_explicit_question_constraints(
        correct_turn["original_question"],
        decision,
    )
    first = next_recipe_step(
        decision,
        completed_tool_names=[],
        current_turn_facts=[],
    )
    first_facts = [
        fact
        for fact in all_correct_facts
        if fact.source_tool == first.tool_name
    ]
    validate_step_facts(first, first_facts)
    second = next_recipe_step(
        decision,
        completed_tool_names=[first.tool_name],
        current_turn_facts=first_facts,
    )
    second_facts = [
        fact
        for fact in all_correct_facts
        if fact.source_tool == second.tool_name
    ]
    validate_step_facts(second, second_facts)

    plan = _plan(
        session_id=record["session_id"],
        turn_id=args.correct_turn_id,
        facts=facts,
    )
    validation = validate_semantic_report_v2_1(plan, facts)
    markdown = render_semantic_report_v2_1(plan, facts)

    failed_outcome = json.loads(
        args.failed_v2_outcome.read_text(encoding="utf-8")
    )
    failed_facts = [
        FactRecord.model_validate(item)
        for item in failed_outcome["facts"]
    ]
    overview_sales = next(
        fact
        for fact in failed_facts
        if (
            fact.source_tool == "get_sales_overview"
            and fact.metric == "sales_amount"
        )
    )
    failed_rank_sales = [
        fact
        for fact in failed_facts
        if (
            fact.source_tool == "rank_products"
            and fact.metric == "sales_amount"
        )
    ]
    counterexample = _plan(
        session_id=failed_outcome["session_id"],
        turn_id=failed_outcome["turn_id"],
        facts=[overview_sales, *failed_rank_sales],
    )
    counterexample.sections[0].blocks[0].fact_ids = [
        overview_sales.fact_id
    ]
    counterexample.sections[1].blocks = [
        SemanticBlockPlanV2_1(
            template_id="peak_period_finding",
            fact_ids=[overview_sales.fact_id],
        )
    ]
    counterexample_validation = validate_semantic_report_v2_1(
        counterexample,
        failed_facts,
    )
    wrong_prefix_rejected = False
    try:
        next_recipe_step(
            decision,
            completed_tool_names=["get_sales_overview"],
            current_turn_facts=failed_facts,
        )
    except RecipeV2_1Error:
        wrong_prefix_rejected = True

    timestamp = datetime.now().astimezone().strftime(
        "%Y%m%dT%H%M%S_%f%z"
    )
    output_dir = args.output_dir or (
        Path("results/raw") / f"v2_1_offline_{timestamp}"
    )
    output_dir.mkdir(parents=True, exist_ok=False)
    _write_json(
        output_dir / "decision.json",
        decision.model_dump(mode="json"),
    )
    _write_json(
        output_dir / "recipe_steps.json",
        [
            {
                "step_id": step.step_id,
                "tool_name": step.tool_name,
                "arguments": step.arguments,
                "required_output_metrics": list(
                    step.required_output_metrics
                ),
                "dependency_fact_ids": list(
                    step.dependency_fact_ids
                ),
            }
            for step in (first, second)
        ],
    )
    _write_json(
        output_dir / "semantic_plan.json",
        plan.model_dump(mode="json"),
    )
    _write_json(
        output_dir / "semantic_validation.json",
        validation.model_dump(mode="json"),
    )
    _write_json(
        output_dir / "counterexample_validation.json",
        counterexample_validation.model_dump(mode="json"),
    )
    (output_dir / "report.md").write_text(
        markdown,
        encoding="utf-8",
    )
    summary = {
        "schema_version": "1.5.6-h3-v2.1-offline-validation-v1",
        "execution_mode": "offline_replay",
        "real_model_called": False,
        "recipe_id": decision.recipe_id,
        "tool_sequence": [first.tool_name, second.tool_name],
        "dependent_fact_ids": list(second.dependency_fact_ids),
        "dependent_period": {
            "start_date": second.arguments["start_date"],
            "end_date": second.arguments["end_date"],
        },
        "semantic_validation_status": validation.status,
        "explicit_question_constraints_passed": True,
        "wrong_tool_prefix_rejected": wrong_prefix_rejected,
        "v2_overview_as_peak_rejected": (
            counterexample_validation.status == "failed"
        ),
        "counterexample_issue_codes": [
            issue.code
            for issue in counterexample_validation.issues
        ],
        "output_dir": output_dir.as_posix(),
    }
    _write_json(output_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
