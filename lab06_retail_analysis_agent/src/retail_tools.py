"""Deterministic implementations of the seven frozen H3 retail tools."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

import pandas as pd

from src.retail_cleaning import RetailDataLayers
from src.tool_schemas import (
    AnalyzeCustomersArguments,
    AnalyzeRegionsArguments,
    AnalyzeTimeTrendArguments,
    CompareSegmentsArguments,
    GetDataProfileArguments,
    GetSalesOverviewArguments,
    RankProductsArguments,
)


MILLI_PER_GBP = Decimal("1000")
DISPLAY_QUANTUM = Decimal("0.01")
INCOMPLETE_PERIODS = ("2011-12",)


def _display_gbp_from_milli(value: int) -> str:
    amount = Decimal(int(value)) / MILLI_PER_GBP
    return format(amount.quantize(DISPLAY_QUANTUM, ROUND_HALF_UP), "f")


def _sales_metrics(frame: pd.DataFrame) -> dict[str, Any]:
    amount_milli = int(frame["line_amount_milli_gbp"].sum())
    order_count = int(frame["invoice_no"].nunique(dropna=True))
    amount = Decimal(amount_milli) / MILLI_PER_GBP
    average = amount / Decimal(order_count) if order_count else Decimal("0")
    return {
        "sales_amount_gbp": _display_gbp_from_milli(amount_milli),
        "sales_quantity_items": int(frame["quantity"].sum()),
        "order_count": order_count,
        "average_order_value_gbp": format(
            average.quantize(DISPLAY_QUANTUM, ROUND_HALF_UP),
            "f",
        ),
    }


def _rank(
    frame: pd.DataFrame,
    *,
    group_columns: list[str],
    metric: str,
    top_n: int,
) -> list[dict[str, Any]]:
    grouped = (
        frame.groupby(group_columns, dropna=False)
        .agg(
            sales_amount_milli_gbp=("line_amount_milli_gbp", "sum"),
            sales_quantity_items=("quantity", "sum"),
            order_count=("invoice_no", "nunique"),
        )
        .reset_index()
    )
    metric_column = {
        "sales_amount": "sales_amount_milli_gbp",
        "sales_quantity": "sales_quantity_items",
        "order_count": "order_count",
        "average_order_value": "average_order_value_milli_gbp",
    }[metric]
    if metric == "average_order_value":
        grouped[metric_column] = (
            grouped["sales_amount_milli_gbp"] / grouped["order_count"]
        )
    grouped = grouped.sort_values(
        [metric_column, *group_columns],
        ascending=[False, *([True] * len(group_columns))],
        kind="stable",
    ).head(top_n)

    records: list[dict[str, Any]] = []
    for raw_row in grouped.to_dict(orient="records"):
        row = dict(raw_row)
        amount_milli = int(row.pop("sales_amount_milli_gbp"))
        row.pop("average_order_value_milli_gbp", None)
        row["sales_quantity_items"] = int(row["sales_quantity_items"])
        row["order_count"] = int(row["order_count"])
        row["sales_amount_gbp"] = _display_gbp_from_milli(amount_milli)
        if metric == "average_order_value":
            average = (
                Decimal(amount_milli) / MILLI_PER_GBP / row["order_count"]
                if row["order_count"]
                else Decimal("0")
            )
            row["average_order_value_gbp"] = format(
                average.quantize(DISPLAY_QUANTUM, ROUND_HALF_UP),
                "f",
            )
        records.append(row)
    return records


class RetailToolService:
    """Read-only service over H2-derived data layers."""

    def __init__(
        self,
        layers: RetailDataLayers,
        *,
        incomplete_periods: tuple[str, ...] = INCOMPLETE_PERIODS,
    ) -> None:
        self.layers = layers
        self.incomplete_periods = incomplete_periods

    def _filter_frame(
        self,
        frame: pd.DataFrame,
        *,
        period: str,
        start_date: str | None,
        end_date: str | None,
    ) -> pd.DataFrame:
        if period == "all_data":
            return frame
        if period == "complete_months_only":
            month = frame["invoice_date"].dt.to_period("M").astype(str)
            return frame.loc[~month.isin(self.incomplete_periods)]

        start = pd.Timestamp(start_date)
        exclusive_end = pd.Timestamp(end_date) + pd.Timedelta(days=1)
        return frame.loc[
            frame["invoice_date"].ge(start)
            & frame["invoice_date"].lt(exclusive_end)
        ]

    def _scope(
        self,
        *,
        fact_layer: str,
        period: str,
        start_date: str | None,
        end_date: str | None,
        row_count: int,
    ) -> dict[str, Any]:
        return {
            "fact_layer": fact_layer,
            "period": period,
            "start_date": start_date,
            "end_date": end_date,
            "row_count": row_count,
        }

    def _result(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        scope: dict[str, Any],
        data: dict[str, Any],
        warnings: list[str] | None = None,
    ) -> dict[str, Any]:
        return {
            "schema_version": "1.5.6-h3-tool-result-v1",
            "tool_name": tool_name,
            "arguments": arguments,
            "analysis_scope": scope,
            "data": data,
            "warnings": warnings or [],
            "privacy": {
                "customer_id_values_exported": False,
                "public_customer_output": "aggregate_only",
            },
        }

    def get_data_profile(
        self,
        arguments: GetDataProfileArguments,
    ) -> dict[str, Any]:
        classified = self.layers.classified
        active = classified.loc[
            ~classified["is_exact_duplicate_after_first"]
        ]
        classification = {
            str(key): int(value)
            for key, value in active["record_class"].value_counts().items()
        }
        summary = {
            "source_rows": int(len(classified)),
            "exact_duplicate_rows_after_first": int(
                classified["is_exact_duplicate_after_first"].sum()
            ),
            "rows_after_keep_first": int(len(active)),
            "sales_fact_rows": int(len(self.layers.sales_fact)),
            "exception_rows": int(len(self.layers.exceptions)),
            "time_minimum": self.layers.sales_fact[
                "invoice_date"
            ].min().isoformat(),
            "time_maximum": self.layers.sales_fact[
                "invoice_date"
            ].max().isoformat(),
            "incomplete_periods": list(self.incomplete_periods),
        }
        sales = self.layers.sales_fact
        customer = self.layers.customer_fact
        total_amount = int(sales["line_amount_milli_gbp"].sum())
        customer_coverage = {
            "known_customer_rows": int(len(customer)),
            "customer_count": int(
                customer["customer_id"].nunique(dropna=True)
            ),
            "sales_row_coverage": round(
                len(customer) / max(len(sales), 1),
                6,
            ),
            "sales_amount_coverage": round(
                int(customer["line_amount_milli_gbp"].sum())
                / max(total_amount, 1),
                6,
            ),
        }
        sections = {
            "summary": summary,
            "classification": classification,
            "customer_coverage": customer_coverage,
        }
        data = sections if arguments.section == "all" else {
            arguments.section: sections[arguments.section]
        }
        return self._result(
            tool_name="get_data_profile",
            arguments=arguments.model_dump(mode="json"),
            scope={
                "fact_layer": "classified+sales_fact+customer_fact",
                "period": "all_data",
                "start_date": None,
                "end_date": None,
                "row_count": int(len(classified)),
            },
            data=data,
        )

    def get_sales_overview(
        self,
        arguments: GetSalesOverviewArguments,
    ) -> dict[str, Any]:
        sales = self._filter_frame(
            self.layers.sales_fact,
            period=arguments.period,
            start_date=arguments.start_date,
            end_date=arguments.end_date,
        )
        data = {
            **_sales_metrics(sales),
            "time_minimum": (
                sales["invoice_date"].min().isoformat()
                if not sales.empty
                else None
            ),
            "time_maximum": (
                sales["invoice_date"].max().isoformat()
                if not sales.empty
                else None
            ),
            "incomplete_period_warning": (
                ",".join(self.incomplete_periods)
                if arguments.include_incomplete_period_warning
                and arguments.period == "all_data"
                else None
            ),
        }
        warnings = []
        if data["incomplete_period_warning"]:
            warnings.append(
                f"{data['incomplete_period_warning']}是不完整期间。"
            )
        return self._result(
            tool_name="get_sales_overview",
            arguments=arguments.model_dump(mode="json"),
            scope=self._scope(
                fact_layer="sales_fact",
                row_count=len(sales),
                **arguments.model_dump(
                    include={"period", "start_date", "end_date"}
                ),
            ),
            data=data,
            warnings=warnings,
        )

    def rank_products(
        self,
        arguments: RankProductsArguments,
    ) -> dict[str, Any]:
        sales = self._filter_frame(
            self.layers.sales_fact,
            period=arguments.period,
            start_date=arguments.start_date,
            end_date=arguments.end_date,
        )
        return self._result(
            tool_name="rank_products",
            arguments=arguments.model_dump(mode="json"),
            scope=self._scope(
                fact_layer="sales_fact",
                row_count=len(sales),
                **arguments.model_dump(
                    include={"period", "start_date", "end_date"}
                ),
            ),
            data={
                "metric": {
                    "sales_amount": "sales_amount_gbp",
                    "sales_quantity": "sales_quantity_items",
                    "order_count": "order_count",
                }[arguments.metric],
                "top_n": arguments.top_n,
                "ranking": _rank(
                    sales,
                    group_columns=["stock_code", "product_name"],
                    metric=arguments.metric,
                    top_n=arguments.top_n,
                ),
            },
        )

    def analyze_regions(
        self,
        arguments: AnalyzeRegionsArguments,
    ) -> dict[str, Any]:
        sales = self._filter_frame(
            self.layers.sales_fact,
            period=arguments.period,
            start_date=arguments.start_date,
            end_date=arguments.end_date,
        )
        if arguments.excluded_country is not None:
            sales = sales.loc[
                sales["country"].ne(arguments.excluded_country)
            ]
        return self._result(
            tool_name="analyze_regions",
            arguments=arguments.model_dump(mode="json"),
            scope=self._scope(
                fact_layer="sales_fact",
                row_count=len(sales),
                **arguments.model_dump(
                    include={"period", "start_date", "end_date"}
                ),
            ),
            data={
                "metric": {
                    "sales_amount": "sales_amount_gbp",
                    "sales_quantity": "sales_quantity_items",
                    "order_count": "order_count",
                }[arguments.metric],
                "excluded_country": arguments.excluded_country,
                "top_n": arguments.top_n,
                "ranking": _rank(
                    sales,
                    group_columns=["country"],
                    metric=arguments.metric,
                    top_n=arguments.top_n,
                ),
            },
        )

    def analyze_time_trend(
        self,
        arguments: AnalyzeTimeTrendArguments,
    ) -> dict[str, Any]:
        sales = self._filter_frame(
            self.layers.sales_fact,
            period=arguments.period,
            start_date=arguments.start_date,
            end_date=arguments.end_date,
        ).copy()
        excluded: list[str] = []
        if arguments.exclude_incomplete_periods:
            month = sales["invoice_date"].dt.to_period("M").astype(str)
            excluded = list(self.incomplete_periods)
            sales = sales.loc[~month.isin(self.incomplete_periods)].copy()
        sales["month"] = sales["invoice_date"].dt.to_period("M").astype(str)
        trend = _rank(
            sales,
            group_columns=["month"],
            metric=arguments.metric,
            top_n=max(int(sales["month"].nunique()), 1),
        )
        trend = sorted(trend, key=lambda row: row["month"])
        metric_key = {
            "sales_amount": "sales_amount_gbp",
            "sales_quantity": "sales_quantity_items",
            "order_count": "order_count",
            "average_order_value": "average_order_value_gbp",
        }[arguments.metric]
        peak = max(
            trend,
            key=lambda row: Decimal(str(row[metric_key])),
            default=None,
        )
        return self._result(
            tool_name="analyze_time_trend",
            arguments=arguments.model_dump(mode="json"),
            scope=self._scope(
                fact_layer="sales_fact",
                row_count=len(sales),
                **arguments.model_dump(
                    include={"period", "start_date", "end_date"}
                ),
            ),
            data={
                "grain": arguments.grain,
                "metric": metric_key,
                "excluded_incomplete_periods": excluded,
                "trend": trend,
                "peak_period": peak["month"] if peak else None,
                "peak_period_metrics": peak,
            },
        )

    def analyze_customers(
        self,
        arguments: AnalyzeCustomersArguments,
    ) -> dict[str, Any]:
        sales = self._filter_frame(
            self.layers.sales_fact,
            period=arguments.period,
            start_date=arguments.start_date,
            end_date=arguments.end_date,
        )
        customer = self._filter_frame(
            self.layers.customer_fact,
            period=arguments.period,
            start_date=arguments.start_date,
            end_date=arguments.end_date,
        )
        total_amount = int(sales["line_amount_milli_gbp"].sum())
        data = {
            **_sales_metrics(customer),
            "customer_count": int(
                customer["customer_id"].nunique(dropna=True)
            ),
            "sales_row_coverage": round(
                len(customer) / max(len(sales), 1),
                6,
            ),
            "sales_amount_coverage": round(
                int(customer["line_amount_milli_gbp"].sum())
                / max(total_amount, 1),
                6,
            ),
            "privacy_note": "不展示原始 CustomerID",
        }
        return self._result(
            tool_name="analyze_customers",
            arguments=arguments.model_dump(mode="json"),
            scope=self._scope(
                fact_layer="customer_fact",
                row_count=len(customer),
                **arguments.model_dump(
                    include={"period", "start_date", "end_date"}
                ),
            ),
            data=data,
        )

    def compare_segments(
        self,
        arguments: CompareSegmentsArguments,
    ) -> dict[str, Any]:
        sales = self._filter_frame(
            self.layers.sales_fact,
            period=arguments.period,
            start_date=arguments.start_date,
            end_date=arguments.end_date,
        )
        uk = sales.loc[sales["country"].eq("United Kingdom")]
        outside = sales.loc[sales["country"].ne("United Kingdom")]
        total_amount = int(sales["line_amount_milli_gbp"].sum())
        uk_amount = int(uk["line_amount_milli_gbp"].sum())
        outside_amount = int(outside["line_amount_milli_gbp"].sum())
        return self._result(
            tool_name="compare_segments",
            arguments=arguments.model_dump(mode="json"),
            scope=self._scope(
                fact_layer="sales_fact",
                row_count=len(sales),
                **arguments.model_dump(
                    include={"period", "start_date", "end_date"}
                ),
            ),
            data={
                "overall": _sales_metrics(sales),
                "united_kingdom": _sales_metrics(uk),
                "outside_united_kingdom": _sales_metrics(outside),
                "united_kingdom_sales_amount_share": round(
                    uk_amount / max(total_amount, 1),
                    6,
                ),
                "outside_united_kingdom_sales_amount_share": round(
                    outside_amount / max(total_amount, 1),
                    6,
                ),
            },
        )
