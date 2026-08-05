"""Offline model double for the independent native-tool orchestrator.

It simulates model decisions, not tool execution.  In particular Q06 reads
the first tool's FACT before generating the second tool's date arguments.
"""

from __future__ import annotations

import calendar
import json
from dataclasses import dataclass
from typing import Any

from src.agent_protocol import (
    BoundaryResponse,
    ChartRequest,
    ClarificationResponse,
    FinalReportResponse,
)
from src.deepseek_client import (
    ChatCompletionResult,
    DeepSeekClientError,
    ProviderToolCall,
)
from src.fact_schema import FactRecord
from src.fixed_question_validation import load_frozen_questions
from src.report_validation import (
    REPORT_SECTION_ORDER,
    ReportClaim,
    ReportDraft,
    ReportSection,
    fact_reference,
)
from src.tool_schemas import TOOL_ARGUMENT_MODELS


ALL_TOOL_NAMES = tuple(TOOL_ARGUMENT_MODELS)


def _result(
    *,
    content: str | None = None,
    tool_name: str | None = None,
    arguments: dict[str, Any] | None = None,
    call_index: int = 1,
) -> ChatCompletionResult:
    calls: tuple[ProviderToolCall, ...] = ()
    finish_reason = "stop"
    if tool_name is not None:
        finish_reason = "tool_calls"
        calls = (
            ProviderToolCall(
                provider_call_id=f"mock-native-{call_index}",
                tool_name=tool_name,
                arguments=arguments or {},
            ),
        )
    return ChatCompletionResult(
        finish_reason=finish_reason,
        content=content,
        tool_calls=calls,
        raw_response={
            "offline_mock": True,
            "phase": "native_tool_v2_1_revision",
            "finish_reason": finish_reason,
            "selected_tool": tool_name,
            "arguments": arguments,
        },
        usage=None,
    )


def _tool_payloads(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        json.loads(message["content"])
        for message in messages
        if message.get("role") == "tool"
    ]


def _facts(messages: list[dict[str, Any]]) -> list[FactRecord]:
    return [
        FactRecord.model_validate(fact)
        for payload in _tool_payloads(messages)
        for fact in payload["facts"]
    ]


def _report_response(
    messages: list[dict[str, Any]],
    question_id: str,
) -> ChatCompletionResult:
    facts = _facts(messages)
    payloads = _tool_payloads(messages)
    if not facts or not payloads:
        raise DeepSeekClientError("mock report requires current-turn FACT")

    references = []
    for payload in payloads:
        first = FactRecord.model_validate(payload["facts"][0])
        references.append(fact_reference(first))
    evidence_text = "；".join(ref.display_value for ref in references)
    claims = {
        REPORT_SECTION_ORDER[0]: ReportClaim(
            statement="问题已通过白名单工具执行确定性分析。",
            evidence=[],
        ),
        REPORT_SECTION_ORDER[1]: ReportClaim(
            statement=f"工具返回的关键证据包括{evidence_text}。",
            evidence=references,
        ),
        REPORT_SECTION_ORDER[2]: ReportClaim(
            statement="报告与图表只使用当前轮工具结果和FACT。",
            evidence=[],
        ),
        REPORT_SECTION_ORDER[3]: ReportClaim(
            statement="现有证据仅支持描述性分析，不支持因果判断。",
            evidence=[],
        ),
        REPORT_SECTION_ORDER[4]: ReportClaim(
            statement="建议结合业务背景人工复核解释与后续行动。",
            evidence=[],
        ),
        REPORT_SECTION_ORDER[5]: ReportClaim(
            statement="结论受固定数据范围与已冻结清洗口径限制。",
            evidence=[],
        ),
    }
    session_id = facts[0].session_id
    turn_id = facts[0].turn_id
    report = ReportDraft(
        schema_version="1.5.6-h3-report-draft-v1",
        session_id=session_id,
        turn_id=turn_id,
        title=f"{question_id} 可追溯经营分析",
        sections=[
            ReportSection(name=name, claims=[claims[name]])
            for name in REPORT_SECTION_ORDER
        ],
    )

    chart_types = {
        "analyze_time_trend": "monthly_line",
        "analyze_regions": "vertical_bar",
        "rank_products": "top_n_horizontal_bar",
        "compare_segments": "two_segment_share_bar",
    }
    chart_requests = [
        ChartRequest(
            call_id=payload["internal_call_id"],
            chart_type=chart_types[payload["tool_name"]],
            title=f"{payload['tool_name']} 确定性结果",
        )
        for payload in payloads
        if payload["tool_name"] in chart_types
    ]
    control = FinalReportResponse(
        response_type="report",
        report=report,
        chart_requests=chart_requests,
    )
    return _result(content=control.model_dump_json())


@dataclass
class FrozenQuestionNativeToolMockClient:
    """A deterministic, network-free model double for Q01-Q10."""

    call_count: int = 0

    def complete_strict_tools(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: str = "auto",
        response_format: dict[str, str] | None = None,
    ) -> ChatCompletionResult:
        self.call_count += 1
        visible = tuple(item["function"]["name"] for item in tools)
        if len(visible) != 7 or set(visible) != set(ALL_TOOL_NAMES):
            raise DeepSeekClientError(
                "offline native mock must receive all seven tools"
            )
        if any(
            item["function"].get("strict") is not True for item in tools
        ):
            raise DeepSeekClientError("offline mock requires strict tools")
        if tool_choice not in {"auto", "none"}:
            raise DeepSeekClientError("offline mock received invalid tool_choice")
        if response_format is not None and (
            tool_choice != "none"
            or response_format != {"type": "json_object"}
        ):
            raise DeepSeekClientError(
                "offline mock received invalid terminal response_format"
            )

        user_question = next(
            message["content"]
            for message in messages
            if message.get("role") == "user"
        )
        questions = load_frozen_questions()
        question_by_text = {
            item["question"]: question_id
            for question_id, item in questions.items()
        }
        try:
            question_id = question_by_text[user_question]
        except KeyError as exc:
            raise DeepSeekClientError(
                "offline mock only supports frozen Q01-Q10"
            ) from exc

        tool_payloads = _tool_payloads(messages)
        step = len(tool_payloads)
        all_data = {
            "period": "all_data",
            "start_date": None,
            "end_date": None,
        }
        single_steps = {
            "Q01": (
                "get_sales_overview",
                {**all_data, "include_incomplete_period_warning": True},
            ),
            "Q02": (
                "rank_products",
                {**all_data, "metric": "sales_amount", "top_n": 5},
            ),
            "Q03": (
                "analyze_regions",
                {
                    **all_data,
                    "metric": "sales_amount",
                    "top_n": 5,
                    "excluded_country": "United Kingdom",
                },
            ),
            "Q04": (
                "analyze_time_trend",
                {
                    "period": "complete_months_only",
                    "start_date": None,
                    "end_date": None,
                    "grain": "month",
                    "metric": "sales_amount",
                    "exclude_incomplete_periods": True,
                },
            ),
        }
        if question_id in single_steps:
            if step == 0:
                name, args = single_steps[question_id]
                return _result(
                    tool_name=name,
                    arguments=args,
                    call_index=self.call_count,
                )
            return _report_response(messages, question_id)

        if question_id == "Q05":
            if step == 0:
                return _result(
                    tool_name="get_sales_overview",
                    arguments={
                        **all_data,
                        "include_incomplete_period_warning": True,
                    },
                    call_index=self.call_count,
                )
            if step == 1:
                return _result(
                    tool_name="compare_segments",
                    arguments={
                        **all_data,
                        "comparison": "united_kingdom_vs_other",
                    },
                    call_index=self.call_count,
                )
            return _report_response(messages, question_id)

        if question_id == "Q06":
            if step == 0:
                return _result(
                    tool_name="analyze_time_trend",
                    arguments={
                        "period": "complete_months_only",
                        "start_date": None,
                        "end_date": None,
                        "grain": "month",
                        "metric": "sales_amount",
                        "exclude_incomplete_periods": True,
                    },
                    call_index=self.call_count,
                )
            if step == 1:
                peak = next(
                    fact.value
                    for fact in _facts(messages)
                    if fact.metric == "peak_period"
                )
                year, month = map(int, peak.split("-"))
                last_day = calendar.monthrange(year, month)[1]
                return _result(
                    tool_name="rank_products",
                    arguments={
                        "period": "custom",
                        "start_date": f"{peak}-01",
                        "end_date": f"{peak}-{last_day:02d}",
                        "metric": "sales_amount",
                        "top_n": 3,
                    },
                    call_index=self.call_count,
                )
            return _report_response(messages, question_id)

        if question_id == "Q07":
            if step == 0:
                return _result(
                    tool_name="get_sales_overview",
                    arguments={
                        **all_data,
                        "include_incomplete_period_warning": True,
                    },
                    call_index=self.call_count,
                )
            if step == 1:
                return _result(
                    tool_name="analyze_customers",
                    arguments={**all_data, "include_coverage": True},
                    call_index=self.call_count,
                )
            return _report_response(messages, question_id)

        if question_id == "Q08":
            response = ClarificationResponse(
                response_type="clarification",
                message="请补充时间范围、核心指标和比较维度或对象。",
                topics=[
                    "time_range",
                    "metric",
                    "comparison_dimension_or_objects",
                ],
            )
            return _result(content=response.model_dump_json())
        if question_id == "Q09":
            response = BoundaryResponse(
                response_type="boundary",
                message="数据缺少成本与利润字段，无法计算利润或利润率。",
                missing_fields=["cost", "profit"],
                supported_alternative="按销售额或销量进行商品排名",
            )
            return _result(content=response.model_dump_json())
        response = BoundaryResponse(
            response_type="boundary",
            message="实验不支持预测和自动补货，且缺少库存与外部驱动字段。",
            missing_fields=["inventory", "external_drivers"],
            supported_alternative="展示历史月度销售趋势并标记2011-12不完整",
            boundary_codes=[
                "forecasting_unsupported",
                "automatic_replenishment_unsupported",
            ],
        )
        return _result(content=response.model_dump_json())
