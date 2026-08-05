"""Deterministic, user-facing presentation built only from validated tool results."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable


METRIC_LABELS = {
    "sales_amount_gbp": "销售额",
    "sales_quantity_items": "销售数量",
    "order_count": "订单数",
    "average_order_value_gbp": "客单价",
}


@dataclass(frozen=True)
class AnswerTable:
    title: str
    rows: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class UserAnswerView:
    direct_answers: tuple[str, ...]
    key_points: tuple[str, ...] = ()
    tables: tuple[AnswerTable, ...] = ()
    notes: tuple[str, ...] = ()


def _money(value: Any) -> str:
    try:
        return f"£{Decimal(str(value)):,.2f}"
    except (InvalidOperation, ValueError):
        return str(value)


def _integer(value: Any, suffix: str = "") -> str:
    try:
        return f"{int(value):,}{suffix}"
    except (TypeError, ValueError):
        return str(value)


def _percent(value: Any) -> str:
    try:
        return f"{Decimal(str(value)) * 100:.2f}%"
    except (InvalidOperation, ValueError):
        return str(value)


def _month(value: Any) -> str:
    text = str(value)
    if len(text) == 7 and text[4] == "-":
        try:
            return f"{int(text[:4])}年{int(text[5:])}月"
        except ValueError:
            pass
    return text


def _metric_value(metric: str, value: Any) -> str:
    if metric in {"sales_amount_gbp", "average_order_value_gbp"}:
        return _money(value)
    if metric == "sales_quantity_items":
        return _integer(value, " 件")
    if metric == "order_count":
        return _integer(value, " 笔")
    return str(value)


def _sales_points(data: dict[str, Any]) -> tuple[str, ...]:
    points: list[str] = []
    if "sales_amount_gbp" in data:
        points.append(f"销售额：**{_money(data['sales_amount_gbp'])}**")
    if "sales_quantity_items" in data:
        points.append(
            f"销售数量：**{_integer(data['sales_quantity_items'], ' 件')}**"
        )
    if "order_count" in data:
        points.append(f"订单数：**{_integer(data['order_count'], ' 笔')}**")
    if "average_order_value_gbp" in data:
        points.append(f"客单价：**{_money(data['average_order_value_gbp'])}**")
    return tuple(points)


def _overview(data: dict[str, Any]) -> UserAnswerView:
    return UserAnswerView(
        direct_answers=(
            f"当前分析范围内的总销售额为 **{_money(data['sales_amount_gbp'])}**，"
            f"共有 **{_integer(data['order_count'], ' 笔订单')}**。",
        ),
        key_points=_sales_points(data),
    )


def _ranking(data: dict[str, Any], *, region: bool) -> UserAnswerView:
    rows = list(data.get("ranking") or [])
    metric = str(data.get("metric") or "sales_amount_gbp")
    metric_label = METRIC_LABELS.get(metric, metric)
    if not rows:
        return UserAnswerView(direct_answers=("当前范围内没有可用于排名的记录。",))
    first = rows[0]
    if region:
        subject = str(first.get("country") or "未知地区")
        direct = (
            f"按{metric_label}排名第一的地区是 **{subject}**，"
            f"{metric_label}为 **{_metric_value(metric, first.get(metric))}**。"
        )
        table_rows = tuple(
            {
                "排名": index,
                "国家或地区": row.get("country"),
                "销售额": _money(row.get("sales_amount_gbp")),
                "销售数量": _integer(row.get("sales_quantity_items"), " 件"),
                "订单数": _integer(row.get("order_count"), " 笔"),
            }
            for index, row in enumerate(rows, 1)
        )
        title = f"地区{metric_label}排名"
    else:
        name = str(first.get("product_name") or "未命名商品")
        code = str(first.get("stock_code") or "未知")
        direct = (
            f"按{metric_label}排名第一的商品是 **{name}**（StockCode：`{code}`），"
            f"{metric_label}为 **{_metric_value(metric, first.get(metric))}**。"
        )
        table_rows = tuple(
            {
                "排名": index,
                "StockCode": row.get("stock_code"),
                "商品": row.get("product_name"),
                "销售额": _money(row.get("sales_amount_gbp")),
                "销售数量": _integer(row.get("sales_quantity_items"), " 件"),
                "订单数": _integer(row.get("order_count"), " 笔"),
            }
            for index, row in enumerate(rows, 1)
        )
        title = f"商品{metric_label}排名"
    return UserAnswerView(
        direct_answers=(direct,),
        tables=(AnswerTable(title=title, rows=table_rows),),
    )


def _trend(
    data: dict[str, Any], arguments: dict[str, Any]
) -> UserAnswerView:
    peak = data.get("peak_period_metrics") or {}
    period = data.get("peak_period")
    metric = str(data.get("metric") or "sales_amount_gbp")
    metric_label = METRIC_LABELS.get(metric, metric)
    if not period or metric not in peak:
        return UserAnswerView(direct_answers=("当前范围内没有可比较的月度记录。",))
    complete_months = bool(data.get("excluded_incomplete_periods")) or (
        arguments.get("period") == "complete_months_only"
        or arguments.get("exclude_incomplete_periods") is True
    )
    period_label = "完整月份" if complete_months else "月份"
    direct = (
        f"{metric_label}最高的{period_label}是 **{_month(period)}**，"
        f"当月{metric_label}为 **{_metric_value(metric, peak[metric])}**。"
    )
    points = tuple(
        point
        for point in (
            (
                f"当月销售数量：**{_integer(peak['sales_quantity_items'], ' 件')}**"
                if "sales_quantity_items" in peak
                else None
            ),
            (
                f"当月订单数：**{_integer(peak['order_count'], ' 笔')}**"
                if "order_count" in peak
                else None
            ),
        )
        if point is not None
    )
    excluded = data.get("excluded_incomplete_periods") or []
    notes = (
        "本次完整月份比较已排除："
        + "、".join(_month(item) for item in excluded)
        if excluded
        else ""
    )
    return UserAnswerView(
        direct_answers=(direct,),
        key_points=points,
        notes=((notes,) if notes else ()),
    )


def _customers(data: dict[str, Any]) -> UserAnswerView:
    direct = (
        f"当前范围内可识别的客户共有 **{_integer(data.get('customer_count'), ' 位')}**；"
        f"这些客户记录覆盖 **{_percent(data.get('sales_row_coverage'))}** 的正常销售记录，"
        f"覆盖 **{_percent(data.get('sales_amount_coverage'))}** 的销售额。"
    )
    return UserAnswerView(
        direct_answers=(direct,),
        key_points=_sales_points(data),
    )


def _overview_and_customers(
    overview: dict[str, Any], customers: dict[str, Any]
) -> UserAnswerView:
    direct = (
        "总体正常销售："
        f"销售额 **{_money(overview.get('sales_amount_gbp'))}**，"
        f"销售数量 **{_integer(overview.get('sales_quantity_items'), ' 件')}**，"
        f"订单数 **{_integer(overview.get('order_count'), ' 笔')}**，"
        f"客单价 **{_money(overview.get('average_order_value_gbp'))}**。",
        "已知客户子集："
        f"覆盖 **{_percent(customers.get('sales_row_coverage'))}** 的销售行和 "
        f"**{_percent(customers.get('sales_amount_coverage'))}** 的销售额，"
        f"包含 **{_integer(customers.get('customer_count'), ' 位客户')}**；"
        f"子集销售额 **{_money(customers.get('sales_amount_gbp'))}**，"
        f"订单数 **{_integer(customers.get('order_count'), ' 笔')}**，"
        f"客单价 **{_money(customers.get('average_order_value_gbp'))}**。",
    )
    rows = (
        {
            "范围": "总体正常销售",
            "客户数": "—",
            "销售行覆盖": "100.00%",
            "销售额覆盖": "100.00%",
            "销售额": _money(overview.get("sales_amount_gbp")),
            "销售数量": _integer(overview.get("sales_quantity_items"), " 件"),
            "订单数": _integer(overview.get("order_count"), " 笔"),
            "客单价": _money(overview.get("average_order_value_gbp")),
        },
        {
            "范围": "已知客户子集",
            "客户数": _integer(customers.get("customer_count"), " 位"),
            "销售行覆盖": _percent(customers.get("sales_row_coverage")),
            "销售额覆盖": _percent(customers.get("sales_amount_coverage")),
            "销售额": _money(customers.get("sales_amount_gbp")),
            "销售数量": _integer(customers.get("sales_quantity_items"), " 件"),
            "订单数": _integer(customers.get("order_count"), " 笔"),
            "客单价": _money(customers.get("average_order_value_gbp")),
        },
    )
    return UserAnswerView(
        direct_answers=direct,
        tables=(AnswerTable(title="总体与已知客户子集", rows=rows),),
    )


def _segments(data: dict[str, Any]) -> UserAnswerView:
    uk = data.get("united_kingdom") or {}
    outside = data.get("outside_united_kingdom") or {}
    uk_share = _percent(data.get("united_kingdom_sales_amount_share"))
    outside_share = _percent(data.get("outside_united_kingdom_sales_amount_share"))
    direct = (
        f"英国销售额为 **{_money(uk.get('sales_amount_gbp'))}**，占整体 **{uk_share}**；"
        f"英国以外销售额为 **{_money(outside.get('sales_amount_gbp'))}**，占 **{outside_share}**。"
    )
    rows = (
        {
            "范围": "英国",
            "销售额": _money(uk.get("sales_amount_gbp")),
            "销售数量": _integer(uk.get("sales_quantity_items"), " 件"),
            "订单数": _integer(uk.get("order_count"), " 笔"),
            "客单价": _money(uk.get("average_order_value_gbp")),
            "销售额占比": uk_share,
        },
        {
            "范围": "英国以外",
            "销售额": _money(outside.get("sales_amount_gbp")),
            "销售数量": _integer(outside.get("sales_quantity_items"), " 件"),
            "订单数": _integer(outside.get("order_count"), " 笔"),
            "客单价": _money(outside.get("average_order_value_gbp")),
            "销售额占比": outside_share,
        },
    )
    return UserAnswerView(
        direct_answers=(direct,),
        tables=(AnswerTable(title="英国与英国以外对比", rows=rows),),
    )


def _profile(data: dict[str, Any]) -> UserAnswerView:
    summary = data.get("summary") or {}
    classification = data.get("classification") or {}
    coverage = data.get("customer_coverage") or {}
    answers: list[str] = []
    points: list[str] = []
    tables: list[AnswerTable] = []
    if summary:
        answers.append(
            f"原始数据共有 **{_integer(summary.get('source_rows'), ' 条记录')}**；"
            f"保留重复记录首条后，形成 **{_integer(summary.get('sales_fact_rows'), ' 条正常销售记录')}**。"
        )
        points.append(
            f"异常或非销售记录：**{_integer(summary.get('exception_rows'), ' 条')}**"
        )
    if classification:
        tables.append(
            AnswerTable(
                title="记录分类",
                rows=tuple(
                    {"分类": key, "记录数": _integer(value)}
                    for key, value in classification.items()
                ),
            )
        )
    if coverage:
        points.append(
            f"可识别客户数：**{_integer(coverage.get('customer_count'), ' 位')}**"
        )
        points.append(
            f"客户记录覆盖率：**{_percent(coverage.get('sales_row_coverage'))}**"
        )
    return UserAnswerView(
        direct_answers=tuple(answers or ["数据概况已经完成。"]),
        key_points=tuple(points),
        tables=tuple(tables),
    )


def _present_call(call: Any) -> UserAnswerView:
    result = call.result
    data = result.get("data") or {}
    arguments = result.get("arguments") or {}
    presenters = {
        "get_data_profile": lambda: _profile(data),
        "get_sales_overview": lambda: _overview(data),
        "rank_products": lambda: _ranking(data, region=False),
        "analyze_regions": lambda: _ranking(data, region=True),
        "analyze_time_trend": lambda: _trend(data, arguments),
        "analyze_customers": lambda: _customers(data),
        "compare_segments": lambda: _segments(data),
    }
    if call.tool_name not in presenters:
        return UserAnswerView(direct_answers=("分析已经完成。",))
    return presenters[call.tool_name]()


def build_user_answer(tool_calls: Iterable[Any]) -> UserAnswerView:
    """Compose a readable view without exposing internal evidence identifiers."""

    calls = tuple(tool_calls)
    by_name = {call.tool_name: call for call in calls}
    call_names = {call.tool_name for call in calls}
    if (
        {"get_sales_overview", "analyze_customers"}.issubset(call_names)
        and call_names.issubset(
            {"get_sales_overview", "analyze_customers", "get_data_profile"}
        )
    ):
        return _overview_and_customers(
            by_name["get_sales_overview"].result.get("data") or {},
            by_name["analyze_customers"].result.get("data") or {},
        )
    parts = tuple(_present_call(call) for call in calls)
    if not parts:
        return UserAnswerView(direct_answers=("分析完成，但没有可展示的工具结果。",))
    return UserAnswerView(
        direct_answers=tuple(
            answer for part in parts for answer in part.direct_answers
        ),
        key_points=tuple(point for part in parts for point in part.key_points),
        tables=tuple(table for part in parts for table in part.tables),
        notes=tuple(note for part in parts for note in part.notes),
    )


__all__ = ["AnswerTable", "UserAnswerView", "build_user_answer"]
