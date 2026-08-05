"""Frozen whitelist registry and program-side validation for H3 tools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

from src.retail_tools import RetailToolService
from src.tool_schemas import TOOL_ARGUMENT_MODELS


class ToolExecutionError(ValueError):
    """Raised before execution when a tool name or arguments are invalid."""


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    argument_model: type[BaseModel]
    handler: Callable[[BaseModel], dict[str, Any]]

    def provider_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "strict": True,
                "parameters": self.argument_model.model_json_schema(),
            },
        }


TOOL_DESCRIPTIONS = {
    "get_data_profile": "查看固定数据范围、清洗分类和已知客户覆盖概况。",
    "get_sales_overview": "按冻结口径计算销售额、销量、订单数和客单价。",
    "rank_products": "按销售额、销量或订单数返回StockCode商品Top N。",
    "analyze_regions": "按Country聚合排名，并可排除一个明确国家。",
    "analyze_time_trend": "按日历月返回历史趋势并识别指定指标峰值。",
    "analyze_customers": "返回已知客户子集的聚合指标和覆盖率，不输出CustomerID。",
    "compare_segments": "在同一口径下比较英国与英国以外销售分段。",
}


class RetailToolRegistry:
    """Allow only seven explicitly registered deterministic tools."""

    def __init__(self, service: RetailToolService) -> None:
        self._definitions = {
            "get_data_profile": ToolDefinition(
                "get_data_profile",
                TOOL_DESCRIPTIONS["get_data_profile"],
                TOOL_ARGUMENT_MODELS["get_data_profile"],
                service.get_data_profile,
            ),
            "get_sales_overview": ToolDefinition(
                "get_sales_overview",
                TOOL_DESCRIPTIONS["get_sales_overview"],
                TOOL_ARGUMENT_MODELS["get_sales_overview"],
                service.get_sales_overview,
            ),
            "rank_products": ToolDefinition(
                "rank_products",
                TOOL_DESCRIPTIONS["rank_products"],
                TOOL_ARGUMENT_MODELS["rank_products"],
                service.rank_products,
            ),
            "analyze_regions": ToolDefinition(
                "analyze_regions",
                TOOL_DESCRIPTIONS["analyze_regions"],
                TOOL_ARGUMENT_MODELS["analyze_regions"],
                service.analyze_regions,
            ),
            "analyze_time_trend": ToolDefinition(
                "analyze_time_trend",
                TOOL_DESCRIPTIONS["analyze_time_trend"],
                TOOL_ARGUMENT_MODELS["analyze_time_trend"],
                service.analyze_time_trend,
            ),
            "analyze_customers": ToolDefinition(
                "analyze_customers",
                TOOL_DESCRIPTIONS["analyze_customers"],
                TOOL_ARGUMENT_MODELS["analyze_customers"],
                service.analyze_customers,
            ),
            "compare_segments": ToolDefinition(
                "compare_segments",
                TOOL_DESCRIPTIONS["compare_segments"],
                TOOL_ARGUMENT_MODELS["compare_segments"],
                service.compare_segments,
            ),
        }

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self._definitions)

    def provider_schemas(self) -> list[dict[str, Any]]:
        return [
            definition.provider_schema()
            for definition in self._definitions.values()
        ]

    def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        definition = self._definitions.get(tool_name)
        if definition is None:
            raise ToolExecutionError(f"工具不在白名单中：{tool_name}")
        try:
            validated = definition.argument_model.model_validate(arguments)
        except ValidationError as exc:
            raise ToolExecutionError(
                f"{tool_name}参数Schema校验失败：{exc}"
            ) from exc
        return definition.handler(validated)
