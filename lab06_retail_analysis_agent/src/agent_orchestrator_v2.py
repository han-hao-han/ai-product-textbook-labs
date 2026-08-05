"""Candidate V2 orchestration with JSON gates and program-finalized values."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from pydantic import ValidationError

from src.agent_decision_v2 import (
    AnalysisDecisionV2,
    BoundaryDecisionV2,
    ClarificationDecisionV2,
    DecisionProtocolError,
    DecisionV2,
    parse_decision_v2,
)
from src.chart_data import ChartData, build_chart_data
from src.deepseek_client import (
    ChatCompletionResult,
    DeepSeekClientError,
)
from src.fact_builder import FactBuildContext, FactBuilder
from src.fact_schema import FactRecord
from src.prompt_contract import (
    ReportBoundaryPromptBundleV2,
    load_report_boundary_prompts_v2,
)
from src.report_finalization_v2 import (
    FinalReportResponseV2,
    FinalizedReportV2,
    ReportPlanValidationV2,
    finalize_report_v2,
    render_finalized_report_v2,
    validate_report_plan_v2,
)


CHART_TOOL_COMPATIBILITY = {
    "monthly_line": "analyze_time_trend",
    "vertical_bar": "analyze_regions",
    "top_n_horizontal_bar": "rank_products",
    "two_segment_share_bar": "compare_segments",
}
DEEPSEEK_UNSUPPORTED_STRICT_KEYWORDS = {
    "minLength",
    "maxLength",
    "minItems",
    "maxItems",
}


class ReportBoundaryV2Error(RuntimeError):
    """Raised when a V2 phase violates the candidate boundary."""


def deepseek_strict_tool_schema(
    provider_schema: dict[str, Any],
) -> dict[str, Any]:
    """Adapt a schema copy to DeepSeek's documented strict subset."""

    adapted = deepcopy(provider_schema)

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            for keyword in DEEPSEEK_UNSUPPORTED_STRICT_KEYWORDS:
                node.pop(keyword, None)
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(adapted)
    return adapted


class V2ModelClient(Protocol):
    def complete_json(
        self,
        *,
        messages: list[dict[str, Any]],
    ) -> ChatCompletionResult: ...

    def complete_strict_tools(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ChatCompletionResult: ...


class V2ToolRegistry(Protocol):
    """Minimal registry surface needed by the candidate orchestrator."""

    def provider_schemas(self) -> list[dict[str, Any]]: ...

    def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class ExecutedToolCall:
    """A lightweight trace record independent of the data runtime."""

    call_id: str
    provider_call_id: str
    tool_name: str
    arguments: dict[str, Any]
    result_path: str
    result: dict[str, Any]
    facts: tuple[FactRecord, ...]


@dataclass(frozen=True)
class AgentTurnOutcomeV2:
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
    decision: DecisionV2 | None = None
    tool_calls: tuple[ExecutedToolCall, ...] = ()
    facts: tuple[FactRecord, ...] = ()
    charts: tuple[ChartData, ...] = ()
    report_response: FinalReportResponseV2 | None = None
    finalized_report: FinalizedReportV2 | None = None
    report_markdown: str | None = None
    report_validation: ReportPlanValidationV2 | None = None
    error_stage: str | None = None
    error_message: str | None = None
    raw_responses: tuple[dict[str, Any], ...] = ()

    @property
    def clarification(self) -> ClarificationDecisionV2 | None:
        if isinstance(self.decision, ClarificationDecisionV2):
            return self.decision
        return None

    @property
    def boundary(self) -> BoundaryDecisionV2 | None:
        if isinstance(self.decision, BoundaryDecisionV2):
            return self.decision
        return None


def _json_system_message(
    prompt: str,
    schema: dict[str, Any],
    *,
    session_id: str,
    turn_id: str,
) -> dict[str, Any]:
    return {
        "role": "system",
        "content": "\n\n".join(
            [
                prompt,
                (
                    "# 当前运行标识\n"
                    f"- session_id: {session_id}\n"
                    f"- turn_id: {turn_id}"
                ),
                (
                    "# 必须遵守的JSON Schema\n"
                    + json.dumps(
                        schema,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                ),
            ]
        ),
    }


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


def _tool_result_message(
    call: ExecutedToolCall,
) -> dict[str, Any]:
    return {
        "role": "tool",
        "tool_call_id": call.provider_call_id,
        "content": json.dumps(
            {
                "internal_call_id": call.call_id,
                "tool_name": call.tool_name,
                "arguments": call.arguments,
                "result": call.result,
                "facts": [
                    fact.model_dump(mode="json")
                    for fact in call.facts
                ],
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    }


def _fact_catalog(facts: list[FactRecord]) -> list[dict[str, Any]]:
    return [
        {
            "fact_id": fact.fact_id,
            "fact_type": fact.fact_type,
            "metric": fact.metric,
            "scope_mode": fact.analysis_scope.period,
            "dimension_names": [
                dimension.name for dimension in fact.dimensions
            ],
            "selection_role": (
                "selected_leader"
                if fact.rank == 1
                else (
                    "ranked_item"
                    if fact.rank is not None
                    else "unranked"
                )
            ),
            "source_tool": fact.source_tool,
            "call_id": fact.call_id,
        }
        for fact in facts
    ]


@dataclass
class RetailAgentOrchestratorV2:
    client: V2ModelClient
    registry: V2ToolRegistry
    prompts: ReportBoundaryPromptBundleV2 = field(
        default_factory=load_report_boundary_prompts_v2
    )

    def run_turn(
        self,
        *,
        session_id: str,
        turn_id: str,
        question: str,
        result_root: str = "results/raw/agent_v2_candidate",
    ) -> AgentTurnOutcomeV2:
        raw_responses: list[dict[str, Any]] = []
        response_count = 0
        try:
            decision_response = self.client.complete_json(
                messages=[
                    _json_system_message(
                        self.prompts.decision_gate.content,
                        {
                            "oneOf": [
                                model.model_json_schema()
                                for model in (
                                    ClarificationDecisionV2,
                                    BoundaryDecisionV2,
                                    AnalysisDecisionV2,
                                )
                            ]
                        },
                        session_id=session_id,
                        turn_id=turn_id,
                    ),
                    {"role": "user", "content": question},
                ]
            )
            response_count += 1
            raw_responses.append(decision_response.raw_response)
            if decision_response.tool_calls:
                raise ReportBoundaryV2Error(
                    "JSON决策门不得返回工具调用"
                )
            if not decision_response.content:
                raise ReportBoundaryV2Error("JSON决策门返回空内容")
            decision = parse_decision_v2(decision_response.content)
        except (
            DeepSeekClientError,
            DecisionProtocolError,
            ReportBoundaryV2Error,
        ) as exc:
            return self._failed(
                session_id=session_id,
                turn_id=turn_id,
                question=question,
                response_count=response_count,
                decision=None,
                calls=[],
                facts=[],
                raw_responses=raw_responses,
                stage="decision_gate",
                error=exc,
            )

        if isinstance(decision, ClarificationDecisionV2):
            return AgentTurnOutcomeV2(
                status="needs_clarification",
                session_id=session_id,
                turn_id=turn_id,
                original_question=question,
                model_response_count=response_count,
                decision=decision,
                raw_responses=tuple(raw_responses),
            )
        if isinstance(decision, BoundaryDecisionV2):
            return AgentTurnOutcomeV2(
                status="boundary",
                session_id=session_id,
                turn_id=turn_id,
                original_question=question,
                model_response_count=response_count,
                decision=decision,
                raw_responses=tuple(raw_responses),
            )

        return self._run_analysis(
            session_id=session_id,
            turn_id=turn_id,
            question=question,
            decision=decision,
            response_count=response_count,
            raw_responses=raw_responses,
            result_root=result_root,
        )

    def _run_analysis(
        self,
        *,
        session_id: str,
        turn_id: str,
        question: str,
        decision: AnalysisDecisionV2,
        response_count: int,
        raw_responses: list[dict[str, Any]],
        result_root: str,
    ) -> AgentTurnOutcomeV2:
        tool_messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": self.prompts.tool_selector.content,
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "question": question,
                        "required_tools_in_order": (
                            decision.required_tools
                        ),
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        schemas = {
            item["function"]["name"]: item
            for item in self.registry.provider_schemas()
        }
        fact_builder = FactBuilder()
        calls: list[ExecutedToolCall] = []
        facts: list[FactRecord] = []

        for expected_tool in decision.required_tools:
            try:
                response = self.client.complete_strict_tools(
                    messages=tool_messages,
                    tools=[
                        deepseek_strict_tool_schema(
                            schemas[expected_tool]
                        )
                    ],
                )
                response_count += 1
                raw_responses.append(response.raw_response)
                if len(response.tool_calls) != 1:
                    raise ReportBoundaryV2Error(
                        "strict工具阶段必须返回且仅返回一个工具调用"
                    )
                provider_call = response.tool_calls[0]
                if provider_call.tool_name != expected_tool:
                    raise ReportBoundaryV2Error(
                        f"计划要求{expected_tool}，模型返回"
                        f"{provider_call.tool_name}"
                    )
                result = self.registry.execute(
                    provider_call.tool_name,
                    provider_call.arguments,
                )
                call_id = f"CALL-{len(calls) + 1:03d}"
                result_path = (
                    f"{result_root.rstrip('/')}/{turn_id}/"
                    f"{call_id}/result.json"
                )
                call_facts = tuple(
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
                executed = ExecutedToolCall(
                    call_id=call_id,
                    provider_call_id=(
                        provider_call.provider_call_id
                    ),
                    tool_name=provider_call.tool_name,
                    arguments=provider_call.arguments,
                    result_path=result_path,
                    result=result,
                    facts=call_facts,
                )
                calls.append(executed)
                facts.extend(call_facts)
                tool_messages.extend(
                    [
                        _assistant_tool_message(response),
                        _tool_result_message(executed),
                    ]
                )
            except (
                DeepSeekClientError,
                ReportBoundaryV2Error,
                ValueError,
            ) as exc:
                return self._failed(
                    session_id=session_id,
                    turn_id=turn_id,
                    question=question,
                    response_count=response_count,
                    decision=decision,
                    calls=calls,
                    facts=facts,
                    raw_responses=raw_responses,
                    stage="strict_tool_phase",
                    error=exc,
                )

        return self._finalize(
            session_id=session_id,
            turn_id=turn_id,
            question=question,
            decision=decision,
            response_count=response_count,
            calls=calls,
            facts=facts,
            raw_responses=raw_responses,
        )

    def _finalize(
        self,
        *,
        session_id: str,
        turn_id: str,
        question: str,
        decision: AnalysisDecisionV2,
        response_count: int,
        calls: list[ExecutedToolCall],
        facts: list[FactRecord],
        raw_responses: list[dict[str, Any]],
    ) -> AgentTurnOutcomeV2:
        try:
            response = self.client.complete_json(
                messages=[
                    _json_system_message(
                        self.prompts.report_finalizer.content,
                        FinalReportResponseV2.model_json_schema(),
                        session_id=session_id,
                        turn_id=turn_id,
                    ),
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "question": question,
                                "required_tools": (
                                    decision.required_tools
                                ),
                                "fact_catalog": _fact_catalog(facts),
                            },
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                    },
                ]
            )
            response_count += 1
            raw_responses.append(response.raw_response)
            if response.tool_calls:
                raise ReportBoundaryV2Error(
                    "JSON报告最终化阶段不得返回工具调用"
                )
            if not response.content:
                raise ReportBoundaryV2Error(
                    "JSON报告最终化阶段返回空内容"
                )
            report_response = (
                FinalReportResponseV2.model_validate_json(
                    response.content
                )
            )
            validation = validate_report_plan_v2(
                report_response,
                facts,
            )
            if validation.status != "passed":
                codes = "、".join(
                    issue.code for issue in validation.issues
                )
                raise ReportBoundaryV2Error(
                    f"V2报告计划校验失败：{codes}"
                )
            finalized = finalize_report_v2(report_response, facts)
            markdown = render_finalized_report_v2(finalized)
            charts = self._build_charts(
                report_response,
                calls,
            )
        except (
            DeepSeekClientError,
            ValidationError,
            ReportBoundaryV2Error,
            ValueError,
        ) as exc:
            return self._failed(
                session_id=session_id,
                turn_id=turn_id,
                question=question,
                response_count=response_count,
                decision=decision,
                calls=calls,
                facts=facts,
                raw_responses=raw_responses,
                stage="report_finalization",
                error=exc,
            )
        return AgentTurnOutcomeV2(
            status="completed",
            session_id=session_id,
            turn_id=turn_id,
            original_question=question,
            model_response_count=response_count,
            decision=decision,
            tool_calls=tuple(calls),
            facts=tuple(facts),
            charts=tuple(charts),
            report_response=report_response,
            finalized_report=finalized,
            report_markdown=markdown,
            report_validation=validation,
            raw_responses=tuple(raw_responses),
        )

    @staticmethod
    def _build_charts(
        response: FinalReportResponseV2,
        calls: list[ExecutedToolCall],
    ) -> list[ChartData]:
        call_by_id = {call.call_id: call for call in calls}
        charts: list[ChartData] = []
        for index, request in enumerate(
            response.chart_requests,
            start=1,
        ):
            call = call_by_id.get(request.call_id)
            if call is None:
                raise ReportBoundaryV2Error(
                    f"图表引用未知CALL：{request.call_id}"
                )
            if (
                CHART_TOOL_COMPATIBILITY[request.chart_type]
                != call.tool_name
            ):
                raise ReportBoundaryV2Error(
                    "图表类型与来源工具不兼容"
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
        decision: DecisionV2 | None,
        calls: list[ExecutedToolCall],
        facts: list[FactRecord],
        raw_responses: list[dict[str, Any]],
        stage: str,
        error: Exception,
    ) -> AgentTurnOutcomeV2:
        return AgentTurnOutcomeV2(
            status="failed",
            session_id=session_id,
            turn_id=turn_id,
            original_question=question,
            model_response_count=response_count,
            decision=decision,
            tool_calls=tuple(calls),
            facts=tuple(facts),
            error_stage=stage,
            error_message=str(error),
            raw_responses=tuple(raw_responses),
        )
