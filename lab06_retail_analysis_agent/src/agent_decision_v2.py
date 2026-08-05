"""JSON decision gate for clarification, boundaries, and tool plans."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    field_validator,
)


ToolName = Literal[
    "get_data_profile",
    "get_sales_overview",
    "rank_products",
    "analyze_regions",
    "analyze_time_trend",
    "analyze_customers",
    "compare_segments",
]


class DecisionProtocolError(ValueError):
    """Raised when the JSON decision gate violates its strict schema."""


class StrictDecisionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ClarificationDecisionV2(StrictDecisionModel):
    decision_type: Literal["clarification"]
    message: str = Field(min_length=1, max_length=1000)
    topics: list[
        Literal[
            "time_range",
            "metric",
            "comparison_dimension_or_objects",
            "top_n",
            "filters",
        ]
    ] = Field(min_length=1, max_length=5)


class BoundaryDecisionV2(StrictDecisionModel):
    decision_type: Literal["boundary"]
    message: str = Field(min_length=1, max_length=1000)
    missing_fields: list[str] = Field(max_length=10)
    supported_alternative: str = Field(min_length=1, max_length=500)


class AnalysisDecisionV2(StrictDecisionModel):
    decision_type: Literal["analysis"]
    required_tools: list[ToolName] = Field(min_length=1, max_length=4)

    @field_validator("required_tools")
    @classmethod
    def validate_unique_tools(
        cls,
        value: list[ToolName],
    ) -> list[ToolName]:
        if len(value) != len(set(value)):
            raise ValueError("required_tools不得重复")
        return value


DecisionV2 = (
    ClarificationDecisionV2
    | BoundaryDecisionV2
    | AnalysisDecisionV2
)
DECISION_ADAPTER = TypeAdapter(DecisionV2)


def parse_decision_v2(content: str) -> DecisionV2:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise DecisionProtocolError("决策门响应不是合法JSON") from exc
    try:
        return DECISION_ADAPTER.validate_python(payload)
    except ValueError as exc:
        raise DecisionProtocolError("决策门响应不符合Schema") from exc
