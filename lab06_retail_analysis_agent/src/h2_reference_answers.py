"""Deterministic reference answers for the candidate H2 question set."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

import pandas as pd

from src.retail_cleaning import RetailDataLayers


MILLI_PER_GBP = Decimal("1000")
DISPLAY_QUANTUM = Decimal("0.01")


def _gbp_from_milli(value: int) -> Decimal:
    return Decimal(int(value)) / MILLI_PER_GBP


def _display_gbp(value: Decimal) -> str:
    return format(value.quantize(DISPLAY_QUANTUM, ROUND_HALF_UP), "f")


def _sales_metrics(frame: pd.DataFrame) -> dict[str, Any]:
    amount = _gbp_from_milli(
        int(frame["line_amount_milli_gbp"].sum())
    )
    orders = int(frame["invoice_no"].nunique(dropna=True))
    average_order_value = (
        amount / Decimal(orders) if orders else Decimal("0")
    )
    return {
        "sales_amount_gbp": _display_gbp(amount),
        "sales_quantity_items": int(frame["quantity"].sum()),
        "order_count": orders,
        "average_order_value_gbp": _display_gbp(
            average_order_value
        ),
    }


def _rank(
    frame: pd.DataFrame,
    *,
    group_columns: list[str],
    top_n: int,
) -> list[dict[str, Any]]:
    grouped = (
        frame.groupby(group_columns, dropna=False)
        .agg(
            sales_amount_milli_gbp=(
                "line_amount_milli_gbp",
                "sum",
            ),
            sales_quantity_items=("quantity", "sum"),
            order_count=("invoice_no", "nunique"),
        )
        .reset_index()
        .sort_values(
            ["sales_amount_milli_gbp", *group_columns],
            ascending=[False, *([True] * len(group_columns))],
            kind="stable",
        )
        .head(top_n)
    )
    records: list[dict[str, Any]] = []
    for row in grouped.to_dict(orient="records"):
        row["sales_amount_gbp"] = _display_gbp(
            _gbp_from_milli(row.pop("sales_amount_milli_gbp"))
        )
        row["sales_quantity_items"] = int(
            row["sales_quantity_items"]
        )
        row["order_count"] = int(row["order_count"])
        records.append(row)
    return records


def build_h2_reference_answers(
    layers: RetailDataLayers,
) -> dict[str, Any]:
    sales = layers.sales_fact.copy()
    customer = layers.customer_fact
    sales["month"] = sales["invoice_date"].dt.to_period("M").astype(str)

    overall = _sales_metrics(sales)
    top_products = _rank(
        sales,
        group_columns=["stock_code", "product_name"],
        top_n=5,
    )
    non_uk = sales.loc[sales["country"].ne("United Kingdom")]
    top_non_uk_countries = _rank(
        non_uk,
        group_columns=["country"],
        top_n=5,
    )

    complete_month_sales = sales.loc[sales["month"].ne("2011-12")]
    month_ranking = _rank(
        complete_month_sales,
        group_columns=["month"],
        top_n=12,
    )
    peak_month = month_ranking[0]["month"]
    peak_month_metrics = next(
        row for row in month_ranking if row["month"] == peak_month
    )

    uk = sales.loc[sales["country"].eq("United Kingdom")]
    uk_metrics = _sales_metrics(uk)
    non_uk_metrics = _sales_metrics(non_uk)
    total_amount_milli = int(sales["line_amount_milli_gbp"].sum())
    uk_amount_milli = int(uk["line_amount_milli_gbp"].sum())
    non_uk_amount_milli = int(non_uk["line_amount_milli_gbp"].sum())

    peak_products = _rank(
        sales.loc[sales["month"].eq(peak_month)],
        group_columns=["stock_code", "product_name"],
        top_n=3,
    )

    customer_metrics = _sales_metrics(customer)
    customer_metrics["customer_count"] = int(
        customer["customer_id"].nunique(dropna=True)
    )
    customer_metrics["sales_row_coverage"] = round(
        len(customer) / max(len(sales), 1),
        6,
    )
    customer_metrics["sales_amount_coverage"] = round(
        int(customer["line_amount_milli_gbp"].sum())
        / max(total_amount_milli, 1),
        6,
    )

    return {
        "schema_version": "1.5.6-h2-reference-answers-v1",
        "basis": {
            "metric_contract": "config/h2_metric_contract.json",
            "customer_id_values_exported": False,
        },
        "answers": {
            "Q01": {
                **overall,
                "time_minimum": sales["invoice_date"].min().isoformat(),
                "time_maximum": sales["invoice_date"].max().isoformat(),
                "incomplete_period_warning": "2011-12",
            },
            "Q02": {
                "metric": "sales_amount_gbp",
                "top_n": 5,
                "ranking": top_products,
            },
            "Q03": {
                "metric": "sales_amount_gbp",
                "excluded_country": "United Kingdom",
                "top_n": 5,
                "ranking": top_non_uk_countries,
            },
            "Q04": {
                "metric": "sales_amount_gbp",
                "excluded_incomplete_period": "2011-12",
                "peak_complete_month": peak_month,
                "peak_month_metrics": peak_month_metrics,
            },
            "Q05": {
                "overall": overall,
                "united_kingdom": uk_metrics,
                "outside_united_kingdom": non_uk_metrics,
                "united_kingdom_sales_amount_share": round(
                    uk_amount_milli / max(total_amount_milli, 1),
                    6,
                ),
                "outside_united_kingdom_sales_amount_share": round(
                    non_uk_amount_milli / max(total_amount_milli, 1),
                    6,
                ),
            },
            "Q06": {
                "peak_complete_month": peak_month,
                "peak_month_metrics": peak_month_metrics,
                "top_3_products_in_peak_month": peak_products,
            },
            "Q07": {
                "overall": overall,
                "known_customer_subset": customer_metrics,
                "privacy_note": "不展示原始 CustomerID",
            },
            "Q08": {
                "expected_outcome": "clarify_once_before_tool_call",
                "required_clarification_topics": [
                    "time_range",
                    "metric",
                    "comparison_dimension_or_objects",
                ],
            },
            "Q09": {
                "expected_outcome": "refuse_unsupported_profit_analysis",
                "missing_fields": ["cost", "profit"],
                "supported_alternative": "按销售额或销量进行商品排名",
            },
            "Q10": {
                "expected_outcome": "refuse_unsupported_forecast",
                "reason": "实验不支持预测，且数据没有预测所需的外部驱动因素",
                "supported_alternative": "展示历史月度销售趋势并标记2011-12不完整",
            },
        },
    }
