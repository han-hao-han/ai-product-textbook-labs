"""Strict non-tool response schemas for the bounded Agent loop."""

from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from src.chart_data import ChartType
from src.report_validation import ReportDraft


class AgentProtocolError(ValueError):
    """Raised when a no-tool model response violates the Agent protocol."""


class StrictAgentModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ClarificationResponse(StrictAgentModel):
    response_type: Literal["clarification"]
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


class BoundaryResponse(StrictAgentModel):
    response_type: Literal["boundary"]
    message: str = Field(min_length=1, max_length=1000)
    missing_fields: list[str] = Field(max_length=10)
    supported_alternative: str = Field(min_length=1, max_length=500)
    boundary_codes: list[
        Literal[
            "forecasting_unsupported",
            "automatic_replenishment_unsupported",
        ]
    ] = Field(default_factory=list, max_length=2)


class ChartRequest(StrictAgentModel):
    call_id: str = Field(pattern=r"^CALL-\d{3,}$")
    chart_type: ChartType
    title: str = Field(min_length=1, max_length=200)


class FinalReportResponse(StrictAgentModel):
    response_type: Literal["report"]
    report: ReportDraft
    chart_requests: list[ChartRequest] = Field(max_length=4)


AgentControlResponse = (
    ClarificationResponse | BoundaryResponse | FinalReportResponse
)
CONTROL_RESPONSE_ADAPTER = TypeAdapter(AgentControlResponse)


def parse_control_response(content: str) -> AgentControlResponse:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        fenced_blocks = re.findall(
            r"```(?:json)?\s*(\{.*?\})\s*```",
            content,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if len(fenced_blocks) != 1:
            raise AgentProtocolError(
                "无工具模型响应不是有效JSON"
            ) from exc
        try:
            payload = json.loads(fenced_blocks[0])
        except json.JSONDecodeError as fenced_exc:
            raise AgentProtocolError(
                "模型代码围栏中的内容不是有效JSON"
            ) from fenced_exc
    try:
        return CONTROL_RESPONSE_ADAPTER.validate_python(payload)
    except ValueError as exc:
        raise AgentProtocolError(
            "无工具模型响应不符合Agent控制Schema"
        ) from exc
