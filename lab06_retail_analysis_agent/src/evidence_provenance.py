"""Program-owned REQUEST and POLICY evidence for report traceability."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictProvenanceModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        validate_assignment=True,
    )


class RequestRecord(StrictProvenanceModel):
    request_id: str = Field(pattern=r"^REQUEST-\d{3,}$")
    session_id: str = Field(pattern=r"^SESSION-[A-Za-z0-9_-]+$")
    turn_id: str = Field(pattern=r"^TURN-\d{3,}$")
    parameter_name: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1, max_length=200)
    source: Literal["validated_user_input"]


class PolicyRecord(StrictProvenanceModel):
    policy_id: str = Field(pattern=r"^POLICY-\d{3,}$")
    code: Literal[
        "aggregate_customer_privacy",
        "incomplete_2011_12",
        "historical_analysis_only",
    ]
    message: str = Field(min_length=1, max_length=500)


def extract_request_records(
    question: str,
    *,
    session_id: str,
    turn_id: str,
) -> list[RequestRecord]:
    """Extract only parameters explicitly present in the user text."""
    values: list[tuple[str, str]] = []
    top_n = re.search(r"前\s*(\d+)\s*个?", question)
    if top_n is not None:
        values.append(("top_n", top_n.group(1)))

    if "销售额" in question:
        values.append(("metric", "sales_amount_gbp"))
    elif "销量" in question:
        values.append(("metric", "sales_quantity_items"))
    elif "订单数" in question:
        values.append(("metric", "order_count"))

    excluded_period = re.search(
        r"排除不完整的(\d{4})年(\d{1,2})月",
        question,
    )
    if excluded_period is not None:
        values.append(
            (
                "excluded_period",
                f"{excluded_period.group(1)}-"
                f"{int(excluded_period.group(2)):02d}",
            )
        )

    excluded_country = re.search(
        r"排除([A-Za-z][A-Za-z ]+?)后",
        question,
    )
    if excluded_country is not None:
        values.append(
            ("excluded_country", excluded_country.group(1).strip())
        )

    return [
        RequestRecord(
            request_id=f"REQUEST-{index:03d}",
            session_id=session_id,
            turn_id=turn_id,
            parameter_name=name,
            value=value,
            source="validated_user_input",
        )
        for index, (name, value) in enumerate(values, start=1)
    ]


def frozen_policy_records() -> list[PolicyRecord]:
    return [
        PolicyRecord(
            policy_id="POLICY-001",
            code="aggregate_customer_privacy",
            message="不展示原始 CustomerID",
        ),
        PolicyRecord(
            policy_id="POLICY-002",
            code="incomplete_2011_12",
            message="2011-12是不完整期间",
        ),
        PolicyRecord(
            policy_id="POLICY-003",
            code="historical_analysis_only",
            message="只支持历史描述性分析，不支持预测或自动补货",
        ),
    ]
