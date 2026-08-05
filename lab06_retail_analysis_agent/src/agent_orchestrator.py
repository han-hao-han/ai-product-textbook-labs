"""Bounded native-tool Agent loop for the frozen H3 contracts."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from src.agent_protocol import (
    AgentProtocolError,
    BoundaryResponse,
    ChartRequest,
    ClarificationResponse,
    FinalReportResponse,
    parse_control_response,
)
from src.chart_data import ChartData, build_chart_data
from src.deepseek_client import (
    ChatCompletionResult,
    DeepSeekClientError,
    ProviderToolCall,
)
from src.evidence_provenance import (
    PolicyRecord,
    RequestRecord,
    extract_request_records,
    frozen_policy_records,
)
from src.fact_builder import FactBuildContext, FactBuilder
from src.fact_schema import FactRecord
from src.prompt_contract import AgentPromptBundle, load_agent_prompts
from src.report_validation import (
    ReportDraft,
    ReportValidationResult,
    render_validated_report,
    validate_report,
)
from src.tool_registry import (
    RetailToolRegistry,
    ToolExecutionError,
)


MAX_TOOL_CALLS_PER_TURN = 4
MAX_TOOL_CALLS_PER_RESPONSE = 1
MAX_CLARIFICATIONS_PER_TURN = 1
CHART_TOOL_COMPATIBILITY = {
    "monthly_line": "analyze_time_trend",
    "vertical_bar": "analyze_regions",
    "top_n_horizontal_bar": "rank_products",
    "two_segment_share_bar": "compare_segments",
}


class AgentOrchestrationError(RuntimeError):
    """Raised when a model or program boundary stops the Agent turn."""


class ChatClient(Protocol):
    def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ChatCompletionResult: ...


@dataclass(frozen=True)
class ExecutedToolCall:
    call_id: str
    provider_call_id: str
    tool_name: str
    arguments: dict[str, Any]
    result_path: str
    result: dict[str, Any]
    facts: tuple[FactRecord, ...]


@dataclass(frozen=True)
class RejectedReportEvidence:
    """Parsed report evidence retained only for failure diagnostics."""

    failure_stage: Literal["report_validation"]
    report_draft: ReportDraft
    report_validation: ReportValidationResult
    chart_requests: tuple[ChartRequest, ...]
    request_records: tuple[RequestRecord, ...]
    policy_records: tuple[PolicyRecord, ...]
    publishable: bool = False
    charts_materialized: bool = False


@dataclass(frozen=True)
class AgentTurnOutcome:
    status: Literal[
        "completed",
        "needs_clarification",
        "boundary",
        "failed",
    ]
    session_id: str
    turn_id: str
    original_question: str
    model_response_count: int
    tool_calls: tuple[ExecutedToolCall, ...] = ()
    facts: tuple[FactRecord, ...] = ()
    charts: tuple[ChartData, ...] = ()
    report_draft: ReportDraft | None = None
    report_markdown: str | None = None
    report_validation: ReportValidationResult | None = None
    clarification: ClarificationResponse | None = None
    boundary: BoundaryResponse | None = None
    error_stage: str | None = None
    error_message: str | None = None
    raw_responses: tuple[dict[str, Any], ...] = ()
    request_records: tuple[RequestRecord, ...] = ()
    policy_records: tuple[PolicyRecord, ...] = ()
    rejected_report_evidence: RejectedReportEvidence | None = None


def _assistant_tool_message(
    response: ChatCompletionResult,
) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": response.content,
        "tool_calls": [
            {
                "id": call.provider_call_id,
                "type": "function",
                "function": {
                    "name": call.tool_name,
                    "arguments": json.dumps(
                        call.arguments,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                },
            }
            for call in response.tool_calls
        ],
    }


def _tool_message(
    call: ProviderToolCall,
    executed: ExecutedToolCall,
    request_records: list[RequestRecord],
    policy_records: list[PolicyRecord],
) -> dict[str, Any]:
    content = {
        "internal_call_id": executed.call_id,
        "tool_name": executed.tool_name,
        "arguments": executed.arguments,
        "result": executed.result,
        "facts": [
            fact.model_dump(mode="json")
            for fact in executed.facts
        ],
        "request_records": [
            item.model_dump(mode="json") for item in request_records
        ],
        "policy_records": [
            item.model_dump(mode="json") for item in policy_records
        ],
        "instruction": (
            "只依据以上确定性结果和FACT决定下一工具或最终报告；"
            "不得自行计算新数值。"
        ),
    }
    return {
        "role": "tool",
        "tool_call_id": call.provider_call_id,
        "content": json.dumps(
            content,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    }


def _runtime_system_prompt(
    prompts: AgentPromptBundle,
    *,
    session_id: str,
    turn_id: str,
) -> str:
    report_schema = FinalReportResponse.model_json_schema()
    return "\n\n".join(
        [
            prompts.system.content,
            prompts.report.content,
            (
                "# 当前运行标识\n"
                f"- session_id: {session_id}\n"
                f"- turn_id: {turn_id}"
            ),
            (
                "# 最终无工具响应JSON Schema\n"
                + json.dumps(
                    report_schema,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            ),
        ]
    )


@dataclass
class RetailAgentOrchestrator:
    client: ChatClient
    registry: RetailToolRegistry
    prompts: AgentPromptBundle = field(
        default_factory=load_agent_prompts
    )
    max_tool_calls_per_turn: int = MAX_TOOL_CALLS_PER_TURN

    def __post_init__(self) -> None:
        if (
            isinstance(self.max_tool_calls_per_turn, bool)
            or not isinstance(self.max_tool_calls_per_turn, int)
            or not 1 <= self.max_tool_calls_per_turn <= 16
        ):
            raise ValueError("每轮工具调用上限必须是1至16之间的整数")

    def run_turn(
        self,
        *,
        session_id: str,
        turn_id: str,
        question: str,
        clarification_count: int = 0,
        clarification_answer: str | None = None,
        result_root: str = "results/raw/online_agent",
    ) -> AgentTurnOutcome:
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": _runtime_system_prompt(
                    self.prompts,
                    session_id=session_id,
                    turn_id=turn_id,
                ),
            },
            {"role": "user", "content": question},
        ]
        if clarification_answer is not None:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "对集中澄清问题的回答："
                        f"{clarification_answer}"
                    ),
                }
            )

        fact_builder = FactBuilder()
        request_records = extract_request_records(
            question,
            session_id=session_id,
            turn_id=turn_id,
        )
        policy_records = frozen_policy_records()
        executed_calls: list[ExecutedToolCall] = []
        all_facts: list[FactRecord] = []
        raw_responses: list[dict[str, Any]] = []
        response_count = 0

        while True:
            try:
                response = self.client.complete(
                    messages=messages,
                    tools=self.registry.provider_schemas(),
                )
            except (DeepSeekClientError, AgentOrchestrationError) as exc:
                return self._failed(
                    session_id=session_id,
                    turn_id=turn_id,
                    question=question,
                    response_count=response_count,
                    executed_calls=executed_calls,
                    all_facts=all_facts,
                    raw_responses=raw_responses,
                    stage="model_response",
                    error=exc,
                )
            response_count += 1
            raw_responses.append(response.raw_response)

            if len(response.tool_calls) > MAX_TOOL_CALLS_PER_RESPONSE:
                return self._failed(
                    session_id=session_id,
                    turn_id=turn_id,
                    question=question,
                    response_count=response_count,
                    executed_calls=executed_calls,
                    all_facts=all_facts,
                    raw_responses=raw_responses,
                    stage="model_response",
                    error=AgentOrchestrationError(
                        "单次模型响应包含多个工具调用，未执行"
                    ),
                )
            if response.tool_calls:
                if len(executed_calls) >= self.max_tool_calls_per_turn:
                    return self._failed(
                        session_id=session_id,
                        turn_id=turn_id,
                        question=question,
                        response_count=response_count,
                        executed_calls=executed_calls,
                        all_facts=all_facts,
                        raw_responses=raw_responses,
                        stage="model_response",
                        error=AgentOrchestrationError(
                            "本轮工具调用已达到"
                            f"{self.max_tool_calls_per_turn}次上限"
                        ),
                    )
                call = response.tool_calls[0]
                call_id = f"CALL-{len(executed_calls) + 1:03d}"
                result_path = (
                    f"{result_root.rstrip('/')}/{turn_id}/"
                    f"{call_id}/result.json"
                )
                if call.tool_name not in self.registry.names:
                    return self._failed(
                        session_id=session_id,
                        turn_id=turn_id,
                        question=question,
                        response_count=response_count,
                        executed_calls=executed_calls,
                        all_facts=all_facts,
                        raw_responses=raw_responses,
                        stage="tool_name",
                        error=AgentOrchestrationError(
                            f"工具不在白名单：{call.tool_name}"
                        ),
                    )
                try:
                    result = self.registry.execute(
                        call.tool_name,
                        call.arguments,
                    )
                except ToolExecutionError as exc:
                    return self._failed(
                        session_id=session_id,
                        turn_id=turn_id,
                        question=question,
                        response_count=response_count,
                        executed_calls=executed_calls,
                        all_facts=all_facts,
                        raw_responses=raw_responses,
                        stage="argument_schema",
                        error=exc,
                    )
                try:
                    facts = tuple(
                        fact_builder.build(
                            result,
                            FactBuildContext(
                                session_id=session_id,
                                turn_id=turn_id,
                                call_id=call_id,
                                source_result_path=result_path,
                            ),
                        )
                    )
                except ValueError as exc:
                    return self._failed(
                        session_id=session_id,
                        turn_id=turn_id,
                        question=question,
                        response_count=response_count,
                        executed_calls=executed_calls,
                        all_facts=all_facts,
                        raw_responses=raw_responses,
                        stage="fact_generation",
                        error=exc,
                    )
                executed = ExecutedToolCall(
                    call_id=call_id,
                    provider_call_id=call.provider_call_id,
                    tool_name=call.tool_name,
                    arguments=call.arguments,
                    result_path=result_path,
                    result=result,
                    facts=facts,
                )
                executed_calls.append(executed)
                all_facts.extend(facts)
                messages.extend(
                    [
                        _assistant_tool_message(response),
                        _tool_message(
                            call,
                            executed,
                            request_records,
                            policy_records,
                        ),
                    ]
                )
                continue

            if response.content is None:
                return self._failed(
                    session_id=session_id,
                    turn_id=turn_id,
                    question=question,
                    response_count=response_count,
                    executed_calls=executed_calls,
                    all_facts=all_facts,
                    raw_responses=raw_responses,
                    stage="model_response",
                    error=AgentOrchestrationError(
                        "模型既未调用工具也未返回控制JSON"
                    ),
                )
            try:
                control = parse_control_response(response.content)
            except AgentProtocolError as exc:
                return self._failed(
                    session_id=session_id,
                    turn_id=turn_id,
                    question=question,
                    response_count=response_count,
                    executed_calls=executed_calls,
                    all_facts=all_facts,
                    raw_responses=raw_responses,
                    stage="model_response",
                    error=exc,
                )
            if isinstance(control, ClarificationResponse):
                if executed_calls:
                    return self._failed(
                        session_id=session_id,
                        turn_id=turn_id,
                        question=question,
                        response_count=response_count,
                        executed_calls=executed_calls,
                        all_facts=all_facts,
                        raw_responses=raw_responses,
                        stage="model_response",
                        error=AgentOrchestrationError(
                            "澄清必须发生在工具调用之前"
                        ),
                    )
                if clarification_count >= MAX_CLARIFICATIONS_PER_TURN:
                    return self._failed(
                        session_id=session_id,
                        turn_id=turn_id,
                        question=question,
                        response_count=response_count,
                        executed_calls=executed_calls,
                        all_facts=all_facts,
                        raw_responses=raw_responses,
                        stage="model_response",
                        error=AgentOrchestrationError(
                            "本轮集中澄清已达到一次上限"
                        ),
                    )
                return AgentTurnOutcome(
                    status="needs_clarification",
                    session_id=session_id,
                    turn_id=turn_id,
                    original_question=question,
                    model_response_count=response_count,
                    clarification=control,
                    raw_responses=tuple(raw_responses),
                    request_records=tuple(request_records),
                    policy_records=tuple(policy_records),
                )
            if isinstance(control, BoundaryResponse):
                if executed_calls:
                    return self._failed(
                        session_id=session_id,
                        turn_id=turn_id,
                        question=question,
                        response_count=response_count,
                        executed_calls=executed_calls,
                        all_facts=all_facts,
                        raw_responses=raw_responses,
                        stage="model_response",
                        error=AgentOrchestrationError(
                            "能力边界应在无关工具调用之前返回"
                        ),
                    )
                return AgentTurnOutcome(
                    status="boundary",
                    session_id=session_id,
                    turn_id=turn_id,
                    original_question=question,
                    model_response_count=response_count,
                    boundary=control,
                    raw_responses=tuple(raw_responses),
                    request_records=tuple(request_records),
                    policy_records=tuple(policy_records),
                )
            return self._complete_report(
                session_id=session_id,
                turn_id=turn_id,
                question=question,
                response_count=response_count,
                control=control,
                executed_calls=executed_calls,
                all_facts=all_facts,
                raw_responses=raw_responses,
                request_records=request_records,
                policy_records=policy_records,
            )

    def _complete_report(
        self,
        *,
        session_id: str,
        turn_id: str,
        question: str,
        response_count: int,
        control: FinalReportResponse,
        executed_calls: list[ExecutedToolCall],
        all_facts: list[FactRecord],
        raw_responses: list[dict[str, Any]],
        request_records: list[RequestRecord],
        policy_records: list[PolicyRecord],
    ) -> AgentTurnOutcome:
        if not executed_calls or not all_facts:
            return self._failed(
                session_id=session_id,
                turn_id=turn_id,
                question=question,
                response_count=response_count,
                executed_calls=executed_calls,
                all_facts=all_facts,
                raw_responses=raw_responses,
                stage="report_validation",
                error=AgentOrchestrationError(
                    "经营报告必须以当前轮工具FACT为依据"
                ),
            )
        if (
            control.report.session_id != session_id
            or control.report.turn_id != turn_id
        ):
            return self._failed(
                session_id=session_id,
                turn_id=turn_id,
                question=question,
                response_count=response_count,
                executed_calls=executed_calls,
                all_facts=all_facts,
                raw_responses=raw_responses,
                stage="report_validation",
                error=AgentOrchestrationError(
                    "报告会话或轮次标识与当前轮不一致"
                ),
            )
        validation = validate_report(
            control.report,
            all_facts,
            request_records,
            policy_records,
        )
        if validation.status != "passed":
            codes = ",".join(
                issue.code for issue in validation.issues
            )
            return self._failed(
                session_id=session_id,
                turn_id=turn_id,
                question=question,
                response_count=response_count,
                executed_calls=executed_calls,
                all_facts=all_facts,
                raw_responses=raw_responses,
                stage="report_validation",
                error=AgentOrchestrationError(
                    f"报告确定性校验失败：{codes}"
                ),
                rejected_report_evidence=RejectedReportEvidence(
                    failure_stage="report_validation",
                    report_draft=control.report,
                    report_validation=validation,
                    chart_requests=tuple(control.chart_requests),
                    request_records=tuple(request_records),
                    policy_records=tuple(policy_records),
                ),
            )
        try:
            charts = self._build_charts(
                control.chart_requests,
                executed_calls,
            )
            report_markdown = render_validated_report(
                control.report,
                all_facts,
                request_records,
                policy_records,
            )
        except (ValueError, AgentOrchestrationError) as exc:
            return self._failed(
                session_id=session_id,
                turn_id=turn_id,
                question=question,
                response_count=response_count,
                executed_calls=executed_calls,
                all_facts=all_facts,
                raw_responses=raw_responses,
                stage="chart_generation",
                error=exc,
            )
        return AgentTurnOutcome(
            status="completed",
            session_id=session_id,
            turn_id=turn_id,
            original_question=question,
            model_response_count=response_count,
            tool_calls=tuple(executed_calls),
            facts=tuple(all_facts),
            charts=tuple(charts),
            report_draft=control.report,
            report_markdown=report_markdown,
            report_validation=validation,
            raw_responses=tuple(raw_responses),
            request_records=tuple(request_records),
            policy_records=tuple(policy_records),
        )

    @staticmethod
    def _build_charts(
        requests: list[ChartRequest],
        calls: list[ExecutedToolCall],
    ) -> list[ChartData]:
        call_by_id = {call.call_id: call for call in calls}
        charts: list[ChartData] = []
        for index, request in enumerate(requests, start=1):
            call = call_by_id.get(request.call_id)
            if call is None:
                raise AgentOrchestrationError(
                    f"图表引用未知CALL：{request.call_id}"
                )
            expected_tool = CHART_TOOL_COMPATIBILITY[
                request.chart_type
            ]
            if call.tool_name != expected_tool:
                raise AgentOrchestrationError(
                    f"{request.chart_type}不能引用{call.tool_name}"
                )
            charts.append(
                build_chart_data(
                    chart_id=f"CHART-{index:03d}",
                    chart_type=request.chart_type,
                    title=request.title,
                    tool_result=call.result,
                    facts=list(call.facts),
                )
            )
        return charts

    @staticmethod
    def _failed(
        *,
        session_id: str,
        turn_id: str,
        question: str,
        response_count: int,
        executed_calls: list[ExecutedToolCall],
        all_facts: list[FactRecord],
        raw_responses: list[dict[str, Any]],
        stage: str,
        error: Exception,
        rejected_report_evidence: RejectedReportEvidence | None = None,
    ) -> AgentTurnOutcome:
        return AgentTurnOutcome(
            status="failed",
            session_id=session_id,
            turn_id=turn_id,
            original_question=question,
            model_response_count=response_count,
            tool_calls=tuple(executed_calls),
            facts=tuple(all_facts),
            error_stage=stage,
            error_message=str(error),
            raw_responses=tuple(raw_responses),
            rejected_report_evidence=rejected_report_evidence,
        )
