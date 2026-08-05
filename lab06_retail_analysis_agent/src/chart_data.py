"""Build and validate chart-ready data from FACT records only."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.fact_schema import FactMetric, FactRecord, FactUnit


ChartType = Literal[
    "monthly_line",
    "vertical_bar",
    "top_n_horizontal_bar",
    "two_segment_share_bar",
]


class ChartDataError(ValueError):
    """Raised when chart data is not traceable to one tool call."""


class StrictChartModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ChartSeries(StrictChartModel):
    name: str = Field(min_length=1, max_length=100)
    values: list[str] = Field(min_length=1, max_length=24)
    fact_ids: list[str] = Field(min_length=1, max_length=24)


class ChartData(StrictChartModel):
    schema_version: Literal["1.5.6-h3-chart-data-v1"]
    chart_id: str = Field(pattern=r"^CHART-\d{3,}$")
    session_id: str = Field(pattern=r"^SESSION-[A-Za-z0-9_-]+$")
    turn_id: str = Field(pattern=r"^TURN-\d{3,}$")
    call_id: str = Field(pattern=r"^CALL-\d{3,}$")
    chart_type: ChartType
    title: str = Field(min_length=1, max_length=200)
    metric: FactMetric
    unit: FactUnit
    categories: list[str] = Field(min_length=1, max_length=24)
    series: list[ChartSeries] = Field(min_length=1, max_length=1)
    source_tool: str = Field(min_length=1, max_length=100)
    source_fact_ids: list[str] = Field(min_length=1, max_length=24)


CHART_SOURCE_TOOLS = {
    "monthly_line": "analyze_time_trend",
    "vertical_bar": "analyze_regions",
    "top_n_horizontal_bar": "rank_products",
    "two_segment_share_bar": "compare_segments",
}

TOOL_RESULT_METRICS = {
    "sales_amount_gbp": "sales_amount",
    "sales_quantity_items": "sales_quantity",
    "order_count": "order_count",
    "average_order_value_gbp": "average_order_value",
}


def _dimension_map(fact: FactRecord) -> dict[str, str]:
    return {item.name: item.value for item in fact.dimensions}


def _category(chart_type: ChartType, fact: FactRecord) -> str:
    dimensions = _dimension_map(fact)
    if chart_type == "monthly_line":
        return dimensions["month"]
    if chart_type == "vertical_bar":
        return dimensions["country"]
    if chart_type == "top_n_horizontal_bar":
        return (
            f"{dimensions['stock_code']} | "
            f"{dimensions['product_name']}"
        )
    if chart_type == "two_segment_share_bar":
        return {
            "united_kingdom": "United Kingdom",
            "outside_united_kingdom": "Outside United Kingdom",
        }[dimensions["segment"]]
    raise ChartDataError(f"不支持的图表类型：{chart_type}")


def _chart_metric(
    chart_type: ChartType,
    tool_result: dict,
) -> FactMetric:
    if chart_type == "two_segment_share_bar":
        return "sales_amount_share"
    try:
        return TOOL_RESULT_METRICS[tool_result["data"]["metric"]]
    except KeyError as exc:
        raise ChartDataError("工具结果没有可绘制的冻结指标") from exc


def build_chart_data(
    *,
    chart_id: str,
    chart_type: ChartType,
    title: str,
    tool_result: dict,
    facts: list[FactRecord],
) -> ChartData:
    expected_tool = CHART_SOURCE_TOOLS[chart_type]
    if tool_result.get("tool_name") != expected_tool:
        raise ChartDataError(
            f"{chart_type}只允许使用{expected_tool}结果"
        )
    if not facts:
        raise ChartDataError("图表至少需要一个FACT")

    session_ids = {fact.session_id for fact in facts}
    turn_ids = {fact.turn_id for fact in facts}
    call_ids = {fact.call_id for fact in facts}
    tools = {fact.source_tool for fact in facts}
    if (
        len(session_ids) != 1
        or len(turn_ids) != 1
        or len(call_ids) != 1
        or tools != {expected_tool}
    ):
        raise ChartDataError("图表FACT必须来自同一会话、轮次和CALL")

    metric = _chart_metric(chart_type, tool_result)
    selected = [fact for fact in facts if fact.metric == metric]
    if not selected:
        raise ChartDataError(f"没有找到图表指标FACT：{metric}")

    if chart_type in {"vertical_bar", "top_n_horizontal_bar"}:
        selected.sort(key=lambda fact: fact.rank or 10**9)
    elif chart_type == "monthly_line":
        selected.sort(key=lambda fact: _dimension_map(fact)["month"])
    else:
        order = {
            "united_kingdom": 0,
            "outside_united_kingdom": 1,
        }
        selected.sort(
            key=lambda fact: order[_dimension_map(fact)["segment"]]
        )

    unit = selected[0].unit
    if any(fact.unit != unit for fact in selected):
        raise ChartDataError("同一图表序列的FACT单位不一致")
    categories = [_category(chart_type, fact) for fact in selected]
    values = [fact.value for fact in selected]
    fact_ids = [fact.fact_id for fact in selected]
    chart = ChartData(
        schema_version="1.5.6-h3-chart-data-v1",
        chart_id=chart_id,
        session_id=selected[0].session_id,
        turn_id=selected[0].turn_id,
        call_id=selected[0].call_id,
        chart_type=chart_type,
        title=title,
        metric=metric,
        unit=unit,
        categories=categories,
        series=[
            ChartSeries(
                name=metric,
                values=values,
                fact_ids=fact_ids,
            )
        ],
        source_tool=expected_tool,
        source_fact_ids=fact_ids,
    )
    validate_chart_data(chart, facts)
    return chart


def validate_chart_data(
    chart: ChartData,
    facts: list[FactRecord],
) -> None:
    fact_by_id = {fact.fact_id: fact for fact in facts}
    if len(fact_by_id) != len(facts):
        raise ChartDataError("FACT ID重复")
    if len(chart.series) != 1:
        raise ChartDataError("当前白名单图表只允许一个序列")
    series = chart.series[0]
    if not (
        len(chart.categories)
        == len(series.values)
        == len(series.fact_ids)
    ):
        raise ChartDataError("图表类别、数值和FACT引用长度不一致")
    if chart.source_fact_ids != series.fact_ids:
        raise ChartDataError("图表来源FACT与序列FACT不一致")

    expected_tool = CHART_SOURCE_TOOLS[chart.chart_type]
    for category, value, fact_id in zip(
        chart.categories,
        series.values,
        series.fact_ids,
        strict=True,
    ):
        fact = fact_by_id.get(fact_id)
        if fact is None:
            raise ChartDataError(f"图表引用不存在的FACT：{fact_id}")
        if (
            fact.session_id != chart.session_id
            or fact.turn_id != chart.turn_id
            or fact.call_id != chart.call_id
        ):
            raise ChartDataError("图表引用了其他会话、轮次或CALL的FACT")
        if fact.source_tool != expected_tool:
            raise ChartDataError("图表FACT来源工具不正确")
        if fact.metric != chart.metric or fact.unit != chart.unit:
            raise ChartDataError("图表指标或单位与FACT不一致")
        if value != fact.value:
            raise ChartDataError("图表数值与FACT不一致")
        if category != _category(chart.chart_type, fact):
            raise ChartDataError("图表类别与FACT维度不一致")
