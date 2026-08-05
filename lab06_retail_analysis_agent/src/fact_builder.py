"""Convert deterministic retail tool results into sequential FACT records."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from src.fact_schema import (
    AnalysisScope,
    FactDimension,
    FactMetric,
    FactRecord,
    FactType,
    FactUnit,
)


class FactBuildError(ValueError):
    """Raised when a tool result cannot satisfy the FACT contract."""


@dataclass(frozen=True)
class FactBuildContext:
    session_id: str
    turn_id: str
    call_id: str
    source_result_path: str


METRIC_FIELDS: dict[str, tuple[FactMetric, FactUnit]] = {
    "sales_amount_gbp": ("sales_amount", "GBP"),
    "sales_quantity_items": ("sales_quantity", "items"),
    "order_count": ("order_count", "orders"),
    "average_order_value_gbp": (
        "average_order_value",
        "GBP_per_order",
    ),
    "customer_count": ("customer_count", "customers"),
    "sales_row_coverage": ("sales_row_coverage", "ratio"),
    "sales_amount_coverage": ("sales_amount_coverage", "ratio"),
    "source_rows": ("source_rows", "rows"),
    "exact_duplicate_rows_after_first": (
        "exact_duplicate_rows_after_first",
        "rows",
    ),
    "rows_after_keep_first": ("rows_after_keep_first", "rows"),
    "sales_fact_rows": ("sales_fact_rows", "rows"),
    "exception_rows": ("exception_rows", "rows"),
    "known_customer_rows": ("known_customer_rows", "rows"),
}


def _canonical_value(value: Any) -> str:
    if isinstance(value, bool) or value is None:
        raise FactBuildError("FACT值不得为布尔值或空值")
    if isinstance(value, float):
        return format(Decimal(str(value)), "f")
    return str(value)


def _display_value(value: str, unit: FactUnit) -> str:
    if unit in {"GBP", "GBP_per_order"}:
        return f"£{Decimal(value):,.2f}"
    if unit in {
        "items",
        "orders",
        "customers",
        "rows",
        "rank_count",
    }:
        return f"{int(value):,}"
    if unit == "ratio":
        percent = (Decimal(value) * 100).quantize(
            Decimal("0.0001"),
            ROUND_HALF_UP,
        )
        return f"{percent}%"
    return value


class FactBuilder:
    """Stateful per-turn FACT ID allocator."""

    def __init__(self, *, start_index: int = 1) -> None:
        if start_index < 1:
            raise ValueError("FACT起始序号必须大于等于1")
        self._next_index = start_index

    @property
    def next_index(self) -> int:
        return self._next_index

    def _emit(
        self,
        *,
        context: FactBuildContext,
        scope: AnalysisScope,
        source_tool: str,
        fact_type: FactType,
        metric: FactMetric,
        raw_value: Any,
        unit: FactUnit,
        dimensions: list[tuple[str, str]] | None = None,
        rank: int | None = None,
    ) -> FactRecord:
        value = _canonical_value(raw_value)
        fact = FactRecord(
            schema_version="1.5.6-h3-fact-v1",
            fact_id=f"FACT-{self._next_index:03d}",
            session_id=context.session_id,
            turn_id=context.turn_id,
            call_id=context.call_id,
            fact_type=fact_type,
            metric=metric,
            value=value,
            display_value=_display_value(value, unit),
            unit=unit,
            analysis_scope=scope,
            dimensions=[
                FactDimension(name=name, value=str(item_value))
                for name, item_value in (dimensions or [])
            ],
            rank=rank,
            source_tool=source_tool,
            source_result_path=context.source_result_path,
        )
        self._next_index += 1
        return fact

    def _emit_metric_fields(
        self,
        *,
        records: list[FactRecord],
        data: dict[str, Any],
        context: FactBuildContext,
        scope: AnalysisScope,
        source_tool: str,
        fact_type: FactType = "metric",
        dimensions: list[tuple[str, str]] | None = None,
        rank: int | None = None,
        rank_metric: FactMetric | None = None,
    ) -> None:
        for field, (metric, unit) in METRIC_FIELDS.items():
            if field not in data:
                continue
            effective_type: FactType = fact_type
            if metric in {
                "sales_row_coverage",
                "sales_amount_coverage",
            }:
                effective_type = "coverage"
            records.append(
                self._emit(
                    context=context,
                    scope=scope,
                    source_tool=source_tool,
                    fact_type=effective_type,
                    metric=metric,
                    raw_value=data[field],
                    unit=unit,
                    dimensions=dimensions,
                    rank=(
                        rank
                        if rank is not None and metric == rank_metric
                        else None
                    ),
                )
            )

    def build(
        self,
        tool_result: dict[str, Any],
        context: FactBuildContext,
    ) -> list[FactRecord]:
        try:
            source_tool = str(tool_result["tool_name"])
            data = tool_result["data"]
            scope = AnalysisScope.model_validate(
                tool_result["analysis_scope"]
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise FactBuildError(f"工具结果结构不完整：{exc}") from exc

        records: list[FactRecord] = []
        handler = getattr(self, f"_build_{source_tool}", None)
        if handler is None:
            raise FactBuildError(f"没有FACT转换规则：{source_tool}")
        handler(records, data, context, scope, source_tool)
        if not records:
            raise FactBuildError(f"{source_tool}没有生成任何FACT")
        return records

    def _build_get_sales_overview(
        self,
        records: list[FactRecord],
        data: dict[str, Any],
        context: FactBuildContext,
        scope: AnalysisScope,
        source_tool: str,
    ) -> None:
        self._emit_metric_fields(
            records=records,
            data=data,
            context=context,
            scope=scope,
            source_tool=source_tool,
        )
        for field, metric, unit in (
            ("time_minimum", "time_minimum", "ISO-8601_datetime"),
            ("time_maximum", "time_maximum", "ISO-8601_datetime"),
            (
                "incomplete_period_warning",
                "incomplete_period",
                "calendar_month",
            ),
        ):
            if data.get(field) is not None:
                records.append(
                    self._emit(
                        context=context,
                        scope=scope,
                        source_tool=source_tool,
                        fact_type="period_marker",
                        metric=metric,
                        raw_value=data[field],
                        unit=unit,
                    )
                )

    def _build_rank_products(
        self,
        records: list[FactRecord],
        data: dict[str, Any],
        context: FactBuildContext,
        scope: AnalysisScope,
        source_tool: str,
    ) -> None:
        records.append(
            self._emit(
                context=context,
                scope=scope,
                source_tool=source_tool,
                fact_type="selection_limit",
                metric="top_n",
                raw_value=data["top_n"],
                unit="rank_count",
            )
        )
        selected_metric = METRIC_FIELDS[data["metric"]][0]
        for rank, row in enumerate(data["ranking"], start=1):
            dimensions = [
                ("stock_code", row["stock_code"]),
                ("product_name", row["product_name"]),
            ]
            self._emit_metric_fields(
                records=records,
                data=row,
                context=context,
                scope=scope,
                source_tool=source_tool,
                fact_type="ranked_metric",
                dimensions=dimensions,
                rank=rank,
                rank_metric=selected_metric,
            )

    def _build_analyze_regions(
        self,
        records: list[FactRecord],
        data: dict[str, Any],
        context: FactBuildContext,
        scope: AnalysisScope,
        source_tool: str,
    ) -> None:
        records.append(
            self._emit(
                context=context,
                scope=scope,
                source_tool=source_tool,
                fact_type="selection_limit",
                metric="top_n",
                raw_value=data["top_n"],
                unit="rank_count",
            )
        )
        selected_metric = METRIC_FIELDS[data["metric"]][0]
        for rank, row in enumerate(data["ranking"], start=1):
            self._emit_metric_fields(
                records=records,
                data=row,
                context=context,
                scope=scope,
                source_tool=source_tool,
                fact_type="ranked_metric",
                dimensions=[("country", row["country"])],
                rank=rank,
                rank_metric=selected_metric,
            )

    def _build_analyze_time_trend(
        self,
        records: list[FactRecord],
        data: dict[str, Any],
        context: FactBuildContext,
        scope: AnalysisScope,
        source_tool: str,
    ) -> None:
        records.append(
            self._emit(
                context=context,
                scope=scope,
                source_tool=source_tool,
                fact_type="period_marker",
                metric="peak_period",
                raw_value=data["peak_period"],
                unit="calendar_month",
                dimensions=[("month", data["peak_period"])],
                rank=1,
            )
        )
        for period in data.get("excluded_incomplete_periods", []):
            records.append(
                self._emit(
                    context=context,
                    scope=scope,
                    source_tool=source_tool,
                    fact_type="period_marker",
                    metric="incomplete_period",
                    raw_value=period,
                    unit="calendar_month",
                )
            )
        selected_metric = {
            "sales_amount_gbp": "sales_amount",
            "sales_quantity_items": "sales_quantity",
            "order_count": "order_count",
            "average_order_value_gbp": "average_order_value",
        }[data["metric"]]
        for row in data["trend"]:
            dimensions = [("month", row["month"])]
            before = len(records)
            self._emit_metric_fields(
                records=records,
                data=row,
                context=context,
                scope=scope,
                source_tool=source_tool,
                dimensions=dimensions,
            )
            if row["month"] == data["peak_period"]:
                for fact in records[before:]:
                    if fact.metric == selected_metric:
                        fact.rank = 1

    def _build_analyze_customers(
        self,
        records: list[FactRecord],
        data: dict[str, Any],
        context: FactBuildContext,
        scope: AnalysisScope,
        source_tool: str,
    ) -> None:
        self._emit_metric_fields(
            records=records,
            data=data,
            context=context,
            scope=scope,
            source_tool=source_tool,
            dimensions=[("segment", "known_customer_subset")],
        )

    def _build_compare_segments(
        self,
        records: list[FactRecord],
        data: dict[str, Any],
        context: FactBuildContext,
        scope: AnalysisScope,
        source_tool: str,
    ) -> None:
        for key, label in (
            ("overall", "overall"),
            ("united_kingdom", "united_kingdom"),
            ("outside_united_kingdom", "outside_united_kingdom"),
        ):
            self._emit_metric_fields(
                records=records,
                data=data[key],
                context=context,
                scope=scope,
                source_tool=source_tool,
                dimensions=[("segment", label)],
            )
        for field, label in (
            (
                "united_kingdom_sales_amount_share",
                "united_kingdom",
            ),
            (
                "outside_united_kingdom_sales_amount_share",
                "outside_united_kingdom",
            ),
        ):
            records.append(
                self._emit(
                    context=context,
                    scope=scope,
                    source_tool=source_tool,
                    fact_type="metric",
                    metric="sales_amount_share",
                    raw_value=data[field],
                    unit="ratio",
                    dimensions=[("segment", label)],
                )
            )

    def _build_get_data_profile(
        self,
        records: list[FactRecord],
        data: dict[str, Any],
        context: FactBuildContext,
        scope: AnalysisScope,
        source_tool: str,
    ) -> None:
        summary = data.get("summary", {})
        self._emit_metric_fields(
            records=records,
            data=summary,
            context=context,
            scope=scope,
            source_tool=source_tool,
            fact_type="profile_count",
            dimensions=[("profile_section", "summary")],
        )
        for field, metric, unit in (
            ("time_minimum", "time_minimum", "ISO-8601_datetime"),
            ("time_maximum", "time_maximum", "ISO-8601_datetime"),
        ):
            if field in summary:
                records.append(
                    self._emit(
                        context=context,
                        scope=scope,
                        source_tool=source_tool,
                        fact_type="period_marker",
                        metric=metric,
                        raw_value=summary[field],
                        unit=unit,
                        dimensions=[("profile_section", "summary")],
                    )
                )
        for period in summary.get("incomplete_periods", []):
            records.append(
                self._emit(
                    context=context,
                    scope=scope,
                    source_tool=source_tool,
                    fact_type="period_marker",
                    metric="incomplete_period",
                    raw_value=period,
                    unit="calendar_month",
                    dimensions=[("profile_section", "summary")],
                )
            )
        for record_class, count in data.get(
            "classification",
            {},
        ).items():
            records.append(
                self._emit(
                    context=context,
                    scope=scope,
                    source_tool=source_tool,
                    fact_type="profile_count",
                    metric="record_class_rows",
                    raw_value=count,
                    unit="rows",
                    dimensions=[
                        ("profile_section", "classification"),
                        ("record_class", record_class),
                    ],
                )
            )
        self._emit_metric_fields(
            records=records,
            data=data.get("customer_coverage", {}),
            context=context,
            scope=scope,
            source_tool=source_tool,
            dimensions=[("profile_section", "customer_coverage")],
        )
