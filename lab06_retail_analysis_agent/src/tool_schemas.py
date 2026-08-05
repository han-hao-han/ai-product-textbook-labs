"""Strict Pydantic argument schemas for the seven H3 retail tools."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


PeriodMode = Literal["all_data", "complete_months_only", "custom"]
RankingMetric = Literal["sales_amount", "sales_quantity", "order_count"]
TrendMetric = Literal[
    "sales_amount",
    "sales_quantity",
    "order_count",
    "average_order_value",
]
IsoDate = str


class StrictToolArguments(BaseModel):
    """Base class shared by every model-callable tool schema."""

    model_config = ConfigDict(extra="forbid", strict=True)


class DateRangeArguments(StrictToolArguments):
    """Required nullable dates keep provider schemas closed and explicit."""

    period: PeriodMode = Field(
        description=(
            "分析期间。all_data=全部数据；complete_months_only=排除冻结的不完整月份；"
            "custom=使用start_date和end_date。"
        )
    )
    start_date: IsoDate | None = Field(
        description="custom期间的开始日期（YYYY-MM-DD，含当日）；其他期间必须为null。"
    )
    end_date: IsoDate | None = Field(
        description="custom期间的结束日期（YYYY-MM-DD，含当日）；其他期间必须为null。"
    )

    @model_validator(mode="after")
    def validate_date_range(self) -> DateRangeArguments:
        if self.period != "custom":
            if self.start_date is not None or self.end_date is not None:
                raise ValueError("非custom期间的start_date和end_date必须为null")
            return self

        if self.start_date is None or self.end_date is None:
            raise ValueError("custom期间必须同时提供start_date和end_date")
        try:
            start = date.fromisoformat(self.start_date)
            end = date.fromisoformat(self.end_date)
        except ValueError as exc:
            raise ValueError("日期必须采用YYYY-MM-DD格式") from exc
        if start > end:
            raise ValueError("start_date不得晚于end_date")
        return self


class GetDataProfileArguments(StrictToolArguments):
    section: Literal[
        "summary",
        "classification",
        "customer_coverage",
        "all",
    ] = Field(description="要查看的数据概况部分。")


class GetSalesOverviewArguments(DateRangeArguments):
    include_incomplete_period_warning: bool = Field(
        description="是否在结果中显式返回不完整期间提醒。"
    )


class RankProductsArguments(DateRangeArguments):
    metric: RankingMetric = Field(description="商品排名使用的冻结指标。")
    top_n: int = Field(ge=1, le=10, description="返回前N名，范围1至10。")


class AnalyzeRegionsArguments(DateRangeArguments):
    metric: RankingMetric = Field(description="地区排名使用的冻结指标。")
    top_n: int = Field(ge=1, le=10, description="返回前N名，范围1至10。")
    excluded_country: str | None = Field(
        min_length=1,
        max_length=100,
        description="需要排除的单一Country值；不排除时为null。",
    )


class AnalyzeTimeTrendArguments(DateRangeArguments):
    grain: Literal["month"] = Field(description="冻结为按日历月聚合。")
    metric: TrendMetric = Field(description="识别峰值月份使用的冻结指标。")
    exclude_incomplete_periods: bool = Field(
        description="是否排除H2冻结的不完整月份。"
    )


class AnalyzeCustomersArguments(DateRangeArguments):
    include_coverage: Literal[True] = Field(
        description="固定为true；客户分析必须同时报告行覆盖率和金额覆盖率。"
    )


class CompareSegmentsArguments(DateRangeArguments):
    comparison: Literal["united_kingdom_vs_other"] = Field(
        description="冻结支持的两分段比较：英国与英国以外。"
    )


TOOL_ARGUMENT_MODELS = {
    "get_data_profile": GetDataProfileArguments,
    "get_sales_overview": GetSalesOverviewArguments,
    "rank_products": RankProductsArguments,
    "analyze_regions": AnalyzeRegionsArguments,
    "analyze_time_trend": AnalyzeTimeTrendArguments,
    "analyze_customers": AnalyzeCustomersArguments,
    "compare_segments": CompareSegmentsArguments,
}
