"""Deterministic current-session condition inheritance and change tracking."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    model_validator,
)


ConditionField = Literal[
    "time_range",
    "metric",
    "analysis_object",
    "comparison_objects",
    "filters",
    "top_n",
]
ConditionStatus = Literal[
    "inherited",
    "added",
    "modified",
    "removed",
]
MetricCondition = Literal[
    "sales_amount",
    "sales_quantity",
    "order_count",
    "average_order_value",
    "customer_count",
]
AnalysisObject = Literal[
    "sales",
    "product",
    "region",
    "time",
    "customer",
    "segments",
]
ConditionValue = (
    str | int | list[str] | dict[str, str | None] | None
)
FIELD_ORDER: tuple[ConditionField, ...] = (
    "time_range",
    "metric",
    "analysis_object",
    "comparison_objects",
    "filters",
    "top_n",
)


class StateTransitionError(ValueError):
    """Raised for ambiguous or invalid condition changes."""


class StrictStateModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        validate_assignment=True,
    )


class TimeRangeCondition(StrictStateModel):
    mode: Literal[
        "all_data",
        "complete_months_only",
        "custom",
    ]
    start_date: str | None
    end_date: str | None

    @model_validator(mode="after")
    def validate_dates(self) -> TimeRangeCondition:
        if self.mode == "custom":
            if self.start_date is None or self.end_date is None:
                raise ValueError("custom时间范围必须同时包含开始和结束日期")
            try:
                start = date.fromisoformat(self.start_date)
                end = date.fromisoformat(self.end_date)
            except ValueError as exc:
                raise ValueError("日期必须采用YYYY-MM-DD格式") from exc
            if start > end:
                raise ValueError("开始日期不得晚于结束日期")
        elif self.start_date is not None or self.end_date is not None:
            raise ValueError("非custom时间范围的日期必须为null")
        return self


class FilterConditions(StrictStateModel):
    excluded_country: str | None = Field(
        min_length=1,
        max_length=100,
    )


class EffectiveConditions(StrictStateModel):
    time_range: TimeRangeCondition | None
    metric: MetricCondition | None
    analysis_object: AnalysisObject | None
    comparison_objects: list[str] | None = Field(
        min_length=2,
        max_length=2,
    )
    filters: FilterConditions | None
    top_n: int | None = Field(ge=1, le=10)

    @classmethod
    def empty(cls) -> EffectiveConditions:
        return cls(
            time_range=None,
            metric=None,
            analysis_object=None,
            comparison_objects=None,
            filters=None,
            top_n=None,
        )


class ConditionOperation(StrictStateModel):
    field: ConditionField
    operation: Literal["set", "remove"]
    value: ConditionValue

    @model_validator(mode="after")
    def validate_operation_value(self) -> ConditionOperation:
        if self.operation == "remove" and self.value is not None:
            raise ValueError("remove操作的value必须为null")
        if self.operation == "set" and self.value is None:
            raise ValueError("set操作必须提供value")
        return self


class ConditionChange(StrictStateModel):
    field: ConditionField
    status: ConditionStatus
    previous_value: ConditionValue
    current_value: ConditionValue


class ConditionResolution(StrictStateModel):
    schema_version: Literal["1.5.6-h3-condition-resolution-v1"]
    previous: EffectiveConditions
    operations: list[ConditionOperation]
    effective: EffectiveConditions
    changes: list[ConditionChange]


FIELD_ADAPTERS: dict[ConditionField, TypeAdapter[Any]] = {
    "time_range": TypeAdapter(TimeRangeCondition),
    "metric": TypeAdapter(MetricCondition),
    "analysis_object": TypeAdapter(AnalysisObject),
    "comparison_objects": TypeAdapter(
        list[str],
        config=ConfigDict(strict=True),
    ),
    "filters": TypeAdapter(FilterConditions),
    "top_n": TypeAdapter(
        int,
        config=ConfigDict(strict=True),
    ),
}


def _parse_field_value(
    field: ConditionField,
    value: ConditionValue,
) -> Any:
    parsed = FIELD_ADAPTERS[field].validate_python(value)
    if field == "comparison_objects" and len(parsed) != 2:
        raise StateTransitionError("comparison_objects必须正好包含两个对象")
    if field == "top_n" and not 1 <= parsed <= 10:
        raise StateTransitionError("top_n必须在1至10之间")
    return parsed


def _json_value(value: Any) -> ConditionValue:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return list(value)
    return value


def resolve_conditions(
    previous: EffectiveConditions,
    operations: list[ConditionOperation],
) -> ConditionResolution:
    seen: set[ConditionField] = set()
    current: dict[str, Any] = {
        field: getattr(previous, field) for field in FIELD_ORDER
    }
    changes_by_field: dict[ConditionField, ConditionChange] = {}

    for operation in operations:
        if operation.field in seen:
            raise StateTransitionError(
                f"同一轮不得重复操作条件：{operation.field}"
            )
        seen.add(operation.field)
        old_value = current[operation.field]
        if operation.operation == "remove":
            if old_value is None:
                raise StateTransitionError(
                    f"无法移除尚未设置的条件：{operation.field}"
                )
            current[operation.field] = None
            status: ConditionStatus = "removed"
            new_value = None
        else:
            try:
                new_value = _parse_field_value(
                    operation.field,
                    operation.value,
                )
            except (ValueError, TypeError) as exc:
                raise StateTransitionError(
                    f"{operation.field}条件值无效：{exc}"
                ) from exc
            current[operation.field] = new_value
            status = (
                "added"
                if old_value is None
                else (
                    "inherited"
                    if old_value == new_value
                    else "modified"
                )
            )
        changes_by_field[operation.field] = ConditionChange(
            field=operation.field,
            status=status,
            previous_value=_json_value(old_value),
            current_value=_json_value(new_value),
        )

    for field in FIELD_ORDER:
        if field in changes_by_field or current[field] is None:
            continue
        value = _json_value(current[field])
        changes_by_field[field] = ConditionChange(
            field=field,
            status="inherited",
            previous_value=value,
            current_value=value,
        )

    effective = EffectiveConditions(**current)
    return ConditionResolution(
        schema_version="1.5.6-h3-condition-resolution-v1",
        previous=previous,
        operations=operations,
        effective=effective,
        changes=[
            changes_by_field[field]
            for field in FIELD_ORDER
            if field in changes_by_field
        ],
    )
