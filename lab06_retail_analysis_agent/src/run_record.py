"""Strict per-turn and per-session run records with privacy checks."""

from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)

from src.chart_data import ChartData
from src.conversation_state import ConditionResolution
from src.fact_schema import FactRecord
from src.report_validation import ReportValidationResult


RunMode = Literal[
    "online_agent",
    "offline_tool_experience",
    "deterministic_validation",
]
SENSITIVE_KEY_PARTS = (
    "api_key",
    "authorization",
    "credential",
    "secret",
    "request_headers",
)
WINDOWS_ABSOLUTE_PATH = re.compile(r"[A-Za-z]:[\\/]")
UNIX_ABSOLUTE_PATH = re.compile(
    r"(?<![:\w])/(?:[^/\s]+/)*[^/\s]+"
)


class RunRecordError(ValueError):
    """Raised when a run record is unsafe or internally inconsistent."""


class StrictRunModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        validate_assignment=True,
    )


def _relative_results_path(value: str) -> str:
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        path.is_absolute()
        or ".." in path.parts
        or ":" in normalized
        or not normalized.startswith("results/")
    ):
        raise ValueError("运行记录路径必须是results/下的仓库相对路径")
    return normalized


class ToolCallRecord(StrictRunModel):
    call_id: str = Field(pattern=r"^CALL-\d{3,}$")
    analysis_target: str = Field(min_length=1, max_length=300)
    reason_summary: str = Field(min_length=1, max_length=500)
    tool_name: str = Field(min_length=1, max_length=100)
    arguments: dict[str, JsonValue]
    model_selected: bool
    status: Literal["succeeded", "failed", "rejected"]
    result_path: str | None
    error_stage: Literal[
        "model_response",
        "tool_name",
        "argument_schema",
        "tool_execution",
        "fact_generation",
        "chart_generation",
        "report_validation",
    ] | None
    error_message: str | None = Field(max_length=1000)

    @field_validator("result_path")
    @classmethod
    def validate_result_path(cls, value: str | None) -> str | None:
        return _relative_results_path(value) if value is not None else None

    @model_validator(mode="after")
    def validate_status_fields(self) -> ToolCallRecord:
        if self.status == "succeeded":
            if self.result_path is None:
                raise ValueError("成功调用必须包含result_path")
            if self.error_stage is not None or self.error_message is not None:
                raise ValueError("成功调用不得包含错误字段")
        elif self.error_stage is None or self.error_message is None:
            raise ValueError("失败或拒绝调用必须包含错误阶段和信息")
        return self


class FailureRecord(StrictRunModel):
    failure_id: str = Field(pattern=r"^FAIL-\d{3,}$")
    call_id: str | None = Field(pattern=r"^CALL-\d{3,}$")
    stage: Literal[
        "model_response",
        "tool_name",
        "argument_schema",
        "tool_execution",
        "fact_generation",
        "chart_generation",
        "report_validation",
        "import_validation",
        "export_validation",
    ]
    error_type: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=1000)
    raw_response_path: str | None

    @field_validator("raw_response_path")
    @classmethod
    def validate_raw_path(cls, value: str | None) -> str | None:
        return _relative_results_path(value) if value is not None else None


class TurnRunRecord(StrictRunModel):
    schema_version: Literal["1.5.6-h3-turn-run-record-v1"]
    session_id: str = Field(pattern=r"^SESSION-[A-Za-z0-9_-]+$")
    turn_id: str = Field(pattern=r"^TURN-\d{3,}$")
    created_at: str
    execution_mode: RunMode
    original_question: str = Field(min_length=1, max_length=2000)
    clarification_question: str | None = Field(max_length=1000)
    clarification_answer: str | None = Field(max_length=1000)
    condition_resolution: ConditionResolution
    tool_calls: list[ToolCallRecord] = Field(max_length=4)
    facts: list[FactRecord]
    charts: list[ChartData]
    report_markdown: str | None = Field(max_length=30000)
    report_validation: ReportValidationResult | None
    failures: list[FailureRecord]
    cross_turn_comparison: bool
    historical_fact_ids_used: list[str]
    raw_model_response_path: str | None
    parsed_tool_calls_path: str | None
    real_model_called: bool

    @field_validator(
        "raw_model_response_path",
        "parsed_tool_calls_path",
    )
    @classmethod
    def validate_optional_path(cls, value: str | None) -> str | None:
        return _relative_results_path(value) if value is not None else None

    @model_validator(mode="after")
    def validate_turn_isolation(self) -> TurnRunRecord:
        if self.historical_fact_ids_used:
            raise ValueError("当前轮不得直接使用历史FACT")
        if self.cross_turn_comparison and not any(
            call.status == "succeeded" for call in self.tool_calls
        ):
            raise ValueError("跨轮比较必须在当前轮重新执行工具")
        call_ids = {call.call_id for call in self.tool_calls}
        if len(call_ids) != len(self.tool_calls):
            raise ValueError("同一轮CALL ID不得重复")
        for fact in self.facts:
            if (
                fact.session_id != self.session_id
                or fact.turn_id != self.turn_id
                or fact.call_id not in call_ids
            ):
                raise ValueError("FACT不属于当前轮已记录CALL")
        fact_ids = {fact.fact_id for fact in self.facts}
        if len(fact_ids) != len(self.facts):
            raise ValueError("同一轮FACT ID不得重复")
        for chart in self.charts:
            if (
                chart.session_id != self.session_id
                or chart.turn_id != self.turn_id
                or chart.call_id not in call_ids
                or not set(chart.source_fact_ids).issubset(fact_ids)
            ):
                raise ValueError("图表不属于当前轮或引用了轮外FACT")
        if (self.report_markdown is None) != (
            self.report_validation is None
        ):
            raise ValueError("报告正文和报告校验必须同时存在或同时为空")
        if (
            self.report_validation is not None
            and self.report_validation.status != "passed"
        ):
            raise ValueError("运行记录不得把未通过校验的报告标为当前报告")
        if self.execution_mode == "offline_tool_experience":
            if self.real_model_called:
                raise ValueError("无模型模式不得记录真实模型调用")
            if self.report_markdown is not None:
                raise ValueError("无模型模式不得生成AI经营报告")
            if any(call.model_selected for call in self.tool_calls):
                raise ValueError("无模型模式不得记录模型选工具")
        return self


class SessionRunRecord(StrictRunModel):
    schema_version: Literal["1.5.6-h3-session-run-record-v1"]
    session_id: str = Field(pattern=r"^SESSION-[A-Za-z0-9_-]+$")
    execution_mode: RunMode
    created_at: str
    updated_at: str
    dataset_name: Literal["UCI Online Retail"]
    dataset_id: Literal[352]
    workbook_sha256: Literal[
        "43465a06f2ccf7c8b5bd2892bc7defb52f97487934fe93b16ae4c3936424676d"
    ]
    metric_contract_version: Literal[
        "1.5.6-h2-metric-contract-v1"
    ]
    model_provider: str | None
    model_id: str | None
    real_model_called: bool
    turns: list[TurnRunRecord] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_session(self) -> SessionRunRecord:
        turn_ids = [turn.turn_id for turn in self.turns]
        if len(turn_ids) != len(set(turn_ids)):
            raise ValueError("会话中的TURN ID不得重复")
        if any(turn.session_id != self.session_id for turn in self.turns):
            raise ValueError("所有轮次必须属于同一会话")
        if any(
            turn.execution_mode != self.execution_mode
            for turn in self.turns
        ):
            raise ValueError("会话和轮次的执行模式必须一致")
        if self.real_model_called != any(
            turn.real_model_called for turn in self.turns
        ):
            raise ValueError("会话模型调用标记与轮次不一致")
        if self.execution_mode == "online_agent":
            if self.model_provider is None or self.model_id is None:
                raise ValueError("在线Agent模式必须记录提供商和模型")
        else:
            if self.real_model_called:
                raise ValueError("非在线Agent模式不得记录真实模型调用")
        return self


def scan_sensitive_content(value: JsonValue, path: str = "$") -> list[str]:
    issues: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = key.lower()
            if any(part in lowered for part in SENSITIVE_KEY_PARTS):
                issues.append(f"{path}.{key}:敏感字段名")
            if lowered == "customer_id":
                issues.append(f"{path}.{key}:禁止导出CustomerID")
            issues.extend(
                scan_sensitive_content(item, f"{path}.{key}")
            )
    elif isinstance(value, list):
        for index, item in enumerate(value):
            issues.extend(
                scan_sensitive_content(item, f"{path}[{index}]")
            )
    elif isinstance(value, str):
        if (
            WINDOWS_ABSOLUTE_PATH.search(value)
            or UNIX_ABSOLUTE_PATH.search(value)
        ):
            issues.append(f"{path}:绝对路径")
        if re.search(r"\bBearer\s+\S+", value, flags=re.IGNORECASE):
            issues.append(f"{path}:Authorization内容")
        if re.search(r"\b(?:sk|ds)-[A-Za-z0-9_-]{12,}", value):
            issues.append(f"{path}:疑似密钥")
    return issues


def validate_record_security(record: SessionRunRecord) -> None:
    payload = record.model_dump(mode="json")
    issues = scan_sensitive_content(payload)
    if issues:
        raise RunRecordError("运行记录安全检查失败：" + "；".join(issues))


def save_session_run_record(
    record: SessionRunRecord,
    output_path: Path,
) -> None:
    validate_record_security(record)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            record.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(output_path)


def load_session_run_record(input_path: Path) -> SessionRunRecord:
    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
        record = SessionRunRecord.model_validate(payload)
        validate_record_security(record)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise RunRecordError(f"运行记录导入失败：{exc}") from exc
    return record
