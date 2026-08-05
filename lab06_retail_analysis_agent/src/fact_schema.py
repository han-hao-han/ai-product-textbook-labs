"""Strict schemas for traceable facts produced from retail tool results."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


FactType = Literal[
    "metric",
    "ranked_metric",
    "coverage",
    "period_marker",
    "profile_count",
    "selection_limit",
]
FactMetric = Literal[
    "sales_amount",
    "sales_quantity",
    "order_count",
    "average_order_value",
    "customer_count",
    "sales_row_coverage",
    "sales_amount_coverage",
    "sales_amount_share",
    "source_rows",
    "exact_duplicate_rows_after_first",
    "rows_after_keep_first",
    "sales_fact_rows",
    "exception_rows",
    "known_customer_rows",
    "record_class_rows",
    "time_minimum",
    "time_maximum",
    "incomplete_period",
    "peak_period",
    "top_n",
]
FactUnit = Literal[
    "GBP",
    "items",
    "orders",
    "GBP_per_order",
    "customers",
    "ratio",
    "rows",
    "ISO-8601_datetime",
    "calendar_month",
    "rank_count",
]
DimensionName = Literal[
    "stock_code",
    "product_name",
    "country",
    "month",
    "segment",
    "profile_section",
    "record_class",
]


class StrictFactModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        validate_assignment=True,
    )


class AnalysisScope(StrictFactModel):
    fact_layer: str = Field(min_length=1, max_length=100)
    period: Literal[
        "all_data",
        "complete_months_only",
        "custom",
    ]
    start_date: str | None
    end_date: str | None
    row_count: int = Field(ge=0)


class FactDimension(StrictFactModel):
    name: DimensionName
    value: str = Field(min_length=1, max_length=200)


class FactRecord(StrictFactModel):
    schema_version: Literal["1.5.6-h3-fact-v1"]
    fact_id: str = Field(pattern=r"^FACT-\d{3,}$")
    session_id: str = Field(pattern=r"^SESSION-[A-Za-z0-9_-]+$")
    turn_id: str = Field(pattern=r"^TURN-\d{3,}$")
    call_id: str = Field(pattern=r"^CALL-\d{3,}$")
    fact_type: FactType
    metric: FactMetric
    value: str = Field(min_length=1, max_length=200)
    display_value: str = Field(min_length=1, max_length=200)
    unit: FactUnit
    analysis_scope: AnalysisScope
    dimensions: list[FactDimension]
    rank: int | None = Field(ge=1)
    source_tool: str = Field(min_length=1, max_length=100)
    source_result_path: str = Field(min_length=1, max_length=500)

    @field_validator("source_result_path")
    @classmethod
    def validate_relative_result_path(cls, value: str) -> str:
        normalized = value.replace("\\", "/")
        path = PurePosixPath(normalized)
        if (
            path.is_absolute()
            or ".." in path.parts
            or ":" in normalized
            or not normalized.startswith("results/")
        ):
            raise ValueError(
                "source_result_path必须是results/下的仓库相对路径"
            )
        return normalized

    @field_validator("dimensions")
    @classmethod
    def validate_dimensions(
        cls,
        value: list[FactDimension],
    ) -> list[FactDimension]:
        names = [item.name for item in value]
        if len(names) != len(set(names)):
            raise ValueError("FACT维度名称不得重复")
        return value
