"""Deterministic analysis recipes and FACT dependency binding for V2.1."""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.fact_schema import FactRecord


RecipeId = Literal[
    "data_profile",
    "sales_overview",
    "product_ranking",
    "region_ranking",
    "peak_complete_month",
    "overview_and_uk_comparison",
    "peak_month_product_ranking",
    "overview_and_customer_coverage",
]
RecipeMetric = Literal[
    "sales_amount",
    "sales_quantity",
    "order_count",
    "average_order_value",
]
PeriodMode = Literal["all_data", "complete_months_only", "custom"]


class RecipeV2_1Error(ValueError):
    """Raised when a recipe cannot be expanded deterministically."""


class StrictRecipeModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        validate_assignment=True,
    )


class AnalysisRecipeDecisionV2_1(StrictRecipeModel):
    decision_type: Literal["analysis_recipe"]
    recipe_id: RecipeId
    period: PeriodMode
    start_date: str | None
    end_date: str | None
    metric: RecipeMetric
    top_n: int | None = Field(ge=1, le=10)
    excluded_country: str | None
    profile_section: Literal[
        "summary",
        "classification",
        "customer_coverage",
        "all",
    ] | None

    @model_validator(mode="after")
    def validate_recipe_inputs(self) -> AnalysisRecipeDecisionV2_1:
        ranking_recipes = {
            "product_ranking",
            "region_ranking",
            "peak_month_product_ranking",
        }
        if self.recipe_id in ranking_recipes and self.top_n is None:
            raise ValueError(f"{self.recipe_id}必须提供top_n")
        if (
            self.recipe_id not in ranking_recipes
            and self.top_n is not None
        ):
            raise ValueError(f"{self.recipe_id}不得提供top_n")
        if (
            self.recipe_id == "region_ranking"
            and self.metric == "average_order_value"
        ):
            raise ValueError("地区排名不支持average_order_value")
        if (
            self.recipe_id
            in {"product_ranking", "peak_month_product_ranking"}
            and self.metric == "average_order_value"
        ):
            raise ValueError("商品排名不支持average_order_value")
        if (
            self.recipe_id == "peak_complete_month"
            and self.period != "complete_months_only"
        ):
            raise ValueError("峰值完整月份配方必须排除不完整月份")
        if self.recipe_id == "peak_month_product_ranking":
            if self.period != "complete_months_only":
                raise ValueError(
                    "峰值月份商品排名配方必须使用完整月份口径"
                )
            if self.metric == "average_order_value":
                raise ValueError(
                    "峰值月份商品排名不支持average_order_value"
                )
        if self.period == "custom":
            if self.start_date is None or self.end_date is None:
                raise ValueError("custom期间必须提供起止日期")
        elif self.start_date is not None or self.end_date is not None:
            raise ValueError("非custom期间不得提供起止日期")
        if (
            self.recipe_id == "data_profile"
            and self.profile_section is None
        ):
            raise ValueError("数据概况配方必须提供profile_section")
        if (
            self.recipe_id != "data_profile"
            and self.profile_section is not None
        ):
            raise ValueError("非数据概况配方不得提供profile_section")
        return self


@dataclass(frozen=True)
class ToolCapabilityV2_1:
    tool_name: str
    operations: tuple[str, ...]
    produced_metrics: tuple[str, ...]


TOOL_CAPABILITIES_V2_1 = {
    "get_data_profile": ToolCapabilityV2_1(
        tool_name="get_data_profile",
        operations=("inspect_data",),
        produced_metrics=("profile_counts", "coverage"),
    ),
    "get_sales_overview": ToolCapabilityV2_1(
        tool_name="get_sales_overview",
        operations=("summarize_sales",),
        produced_metrics=(
            "sales_amount",
            "sales_quantity",
            "order_count",
            "average_order_value",
            "time_range",
        ),
    ),
    "rank_products": ToolCapabilityV2_1(
        tool_name="rank_products",
        operations=("rank_products",),
        produced_metrics=(
            "sales_amount",
            "sales_quantity",
            "order_count",
        ),
    ),
    "analyze_regions": ToolCapabilityV2_1(
        tool_name="analyze_regions",
        operations=("rank_regions",),
        produced_metrics=(
            "sales_amount",
            "sales_quantity",
            "order_count",
        ),
    ),
    "analyze_time_trend": ToolCapabilityV2_1(
        tool_name="analyze_time_trend",
        operations=("find_peak_period", "build_time_trend"),
        produced_metrics=(
            "peak_period",
            "sales_amount",
            "sales_quantity",
            "order_count",
            "average_order_value",
        ),
    ),
    "analyze_customers": ToolCapabilityV2_1(
        tool_name="analyze_customers",
        operations=("summarize_customer_coverage",),
        produced_metrics=("customer_metrics", "coverage"),
    ),
    "compare_segments": ToolCapabilityV2_1(
        tool_name="compare_segments",
        operations=("compare_uk_vs_other",),
        produced_metrics=(
            "sales_amount",
            "sales_quantity",
            "order_count",
            "average_order_value",
            "sales_amount_share",
        ),
    ),
}


RECIPE_TOOL_SEQUENCE_V2_1: dict[RecipeId, tuple[str, ...]] = {
    "data_profile": ("get_data_profile",),
    "sales_overview": ("get_sales_overview",),
    "product_ranking": ("rank_products",),
    "region_ranking": ("analyze_regions",),
    "peak_complete_month": ("analyze_time_trend",),
    "overview_and_uk_comparison": (
        "get_sales_overview",
        "compare_segments",
    ),
    "peak_month_product_ranking": (
        "analyze_time_trend",
        "rank_products",
    ),
    "overview_and_customer_coverage": (
        "get_sales_overview",
        "analyze_customers",
    ),
}


@dataclass(frozen=True)
class PlannedToolStepV2_1:
    step_id: str
    tool_name: str
    arguments: dict[str, Any]
    required_output_metrics: tuple[str, ...]
    dependency_fact_ids: tuple[str, ...] = ()


def _date_arguments(
    decision: AnalysisRecipeDecisionV2_1,
) -> dict[str, Any]:
    return {
        "period": decision.period,
        "start_date": decision.start_date,
        "end_date": decision.end_date,
    }


def _ranking_metric(metric: RecipeMetric) -> str:
    if metric == "average_order_value":
        raise RecipeV2_1Error("当前排名工具不支持客单价")
    return metric


def _peak_fact(facts: list[FactRecord]) -> FactRecord:
    candidates = [
        fact
        for fact in facts
        if (
            fact.source_tool == "analyze_time_trend"
            and fact.metric == "peak_period"
        )
    ]
    if len(candidates) != 1:
        raise RecipeV2_1Error(
            "依赖步骤要求且仅允许一个analyze_time_trend峰值FACT"
        )
    return candidates[0]


def _validate_completed_prefix(
    decision: AnalysisRecipeDecisionV2_1,
    completed_tool_names: list[str],
) -> tuple[str, ...]:
    sequence = RECIPE_TOOL_SEQUENCE_V2_1[decision.recipe_id]
    if tuple(completed_tool_names) != sequence[
        : len(completed_tool_names)
    ]:
        raise RecipeV2_1Error(
            "已完成工具序列不是冻结分析配方的合法前缀"
        )
    if len(completed_tool_names) >= len(sequence):
        raise RecipeV2_1Error("分析配方已经完成")
    return sequence


def next_recipe_step(
    decision: AnalysisRecipeDecisionV2_1,
    *,
    completed_tool_names: list[str],
    current_turn_facts: list[FactRecord],
) -> PlannedToolStepV2_1:
    """Return the next exact tool and bind any FACT dependency."""

    sequence = _validate_completed_prefix(
        decision,
        completed_tool_names,
    )
    index = len(completed_tool_names)
    tool_name = sequence[index]
    base = _date_arguments(decision)
    dependency_ids: tuple[str, ...] = ()

    if tool_name == "get_data_profile":
        arguments = {"section": decision.profile_section}
        required = ()
    elif tool_name == "get_sales_overview":
        arguments = {
            **base,
            "include_incomplete_period_warning": True,
        }
        required = (
            "sales_amount",
            "sales_quantity",
            "order_count",
            "average_order_value",
        )
    elif tool_name == "rank_products":
        if decision.recipe_id == "peak_month_product_ranking":
            peak = _peak_fact(current_turn_facts)
            year, month = map(int, peak.value.split("-"))
            last_day = calendar.monthrange(year, month)[1]
            base = {
                "period": "custom",
                "start_date": f"{peak.value}-01",
                "end_date": f"{peak.value}-{last_day:02d}",
            }
            dependency_ids = (peak.fact_id,)
        arguments = {
            **base,
            "metric": _ranking_metric(decision.metric),
            "top_n": decision.top_n,
        }
        required = (_ranking_metric(decision.metric),)
    elif tool_name == "analyze_regions":
        arguments = {
            **base,
            "metric": _ranking_metric(decision.metric),
            "top_n": decision.top_n,
            "excluded_country": decision.excluded_country,
        }
        required = (_ranking_metric(decision.metric),)
    elif tool_name == "analyze_time_trend":
        arguments = {
            **base,
            "grain": "month",
            "metric": decision.metric,
            "exclude_incomplete_periods": (
                decision.period == "complete_months_only"
            ),
        }
        required = ("peak_period", decision.metric)
    elif tool_name == "analyze_customers":
        arguments = {**base, "include_coverage": True}
        required = (
            "customer_count",
            "sales_row_coverage",
            "sales_amount_coverage",
        )
    elif tool_name == "compare_segments":
        arguments = {
            **base,
            "comparison": "united_kingdom_vs_other",
        }
        required = ("sales_amount_share",)
    else:
        raise RecipeV2_1Error(f"未知配方工具：{tool_name}")

    return PlannedToolStepV2_1(
        step_id=f"STEP-{index + 1:03d}",
        tool_name=tool_name,
        arguments=arguments,
        required_output_metrics=required,
        dependency_fact_ids=dependency_ids,
    )


def validate_step_facts(
    step: PlannedToolStepV2_1,
    facts: list[FactRecord],
) -> None:
    source_facts = [
        fact for fact in facts if fact.source_tool == step.tool_name
    ]
    if not source_facts:
        raise RecipeV2_1Error("工具没有生成任何配方所需FACT")
    observed = {
        fact.metric
        for fact in source_facts
    }
    missing = [
        metric
        for metric in step.required_output_metrics
        if metric not in observed
    ]
    if missing:
        raise RecipeV2_1Error(
            "工具结果没有满足配方要求的FACT："
            + "、".join(missing)
        )


def validate_explicit_question_constraints(
    question: str,
    decision: AnalysisRecipeDecisionV2_1,
) -> None:
    """Reject plans contradicting explicit high-risk user wording."""

    normalized = re.sub(r"\s+", "", question)
    metric_patterns = (
        (r"按销售额|销售额最高", "sales_amount"),
        (r"按销量|销量最高|销售数量最高", "sales_quantity"),
        (r"按订单数|订单数最高", "order_count"),
        (r"按客单价|客单价最高", "average_order_value"),
    )
    explicit_metrics = {
        metric
        for pattern, metric in metric_patterns
        if re.search(pattern, normalized)
    }
    if len(explicit_metrics) == 1:
        expected_metric = next(iter(explicit_metrics))
        if decision.metric != expected_metric:
            raise RecipeV2_1Error(
                "配方指标与用户明确指定的指标不一致"
            )

    top_match = re.search(r"前(10|[1-9])个?", normalized)
    if top_match is not None:
        expected_top_n = int(top_match.group(1))
        if decision.top_n != expected_top_n:
            raise RecipeV2_1Error(
                "配方top_n与用户明确指定的数量不一致"
            )

    requires_peak_product_dependency = (
        "完整月份" in normalized
        and "该月" in normalized
        and "商品" in normalized
        and ("最高" in normalized or "峰值" in normalized)
    )
    if (
        requires_peak_product_dependency
        and decision.recipe_id != "peak_month_product_ranking"
    ):
        raise RecipeV2_1Error(
            "问题明确要求峰值完整月份到商品排名的依赖配方"
        )
