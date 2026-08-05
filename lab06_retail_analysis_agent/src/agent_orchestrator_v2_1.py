"""Independent V2.1 orchestrator for recipe and semantic-plan validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from pydantic import ValidationError

from src.agent_decision_v2 import (
    BoundaryDecisionV2,
    ClarificationDecisionV2,
)
from src.agent_decision_v2_1 import (
    DecisionProtocolV2_1Error,
    DecisionV2_1,
    parse_decision_v2_1,
)
from src.agent_orchestrator_v2 import deepseek_strict_tool_schema
from src.analysis_recipes_v2_1 import (
    RECIPE_TOOL_SEQUENCE_V2_1,
    AnalysisRecipeDecisionV2_1,
    PlannedToolStepV2_1,
    RecipeV2_1Error,
    next_recipe_step,
    validate_explicit_question_constraints,
    validate_step_facts,
)
from src.deepseek_client import (
    ChatCompletionResult,
    DeepSeekClientError,
)
from src.fact_builder import FactBuildContext, FactBuilder
from src.fact_schema import FactRecord
from src.prompt_contract import load_report_boundary_prompts_v2_1
from src.report_semantics_v2_1 import (
    SemanticReportPlanV2_1,
    SemanticValidationV2_1,
    render_semantic_report_v2_1,
    validate_semantic_report_v2_1,
)


class V2_1OrchestrationError(RuntimeError):
    """Raised when a V2.1 program boundary stops the turn."""


class V2_1ModelClient(Protocol):
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


class V2_1ToolRegistry(Protocol):
    def provider_schemas(self) -> list[dict[str, Any]]: ...

    def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class ExecutedToolCallV2_1:
    call_id: str
    provider_call_id: str
    tool_name: str
    arguments: dict[str, Any]
    result_path: str
    result: dict[str, Any]
    facts: tuple[FactRecord, ...]
    dependency_fact_ids: tuple[str, ...]


@dataclass(frozen=True)
class AgentTurnOutcomeV2_1:
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
    decision: DecisionV2_1 | None = None
    tool_calls: tuple[ExecutedToolCallV2_1, ...] = ()
    facts: tuple[FactRecord, ...] = ()
    report_plan: SemanticReportPlanV2_1 | None = None
    report_validation: SemanticValidationV2_1 | None = None
    report_markdown: str | None = None
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


def _response_raw(response: ChatCompletionResult) -> dict[str, Any]:
    return response.raw_response


def _tool_message(
    step: PlannedToolStepV2_1,
    facts: list[FactRecord],
) -> list[dict[str, Any]]:
    return [
        {
            "role": "system",
            "content": (
                "只能调用程序提供的唯一strict工具。"
                "工具名和全部参数必须与step_contract精确一致。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "phase": "strict_recipe_step",
                    "step_contract": {
                        "step_id": step.step_id,
                        "tool_name": step.tool_name,
                        "arguments": step.arguments,
                        "required_output_metrics": list(
                            step.required_output_metrics
                        ),
                        "dependency_fact_ids": list(
                            step.dependency_fact_ids
                        ),
                    },
                    "current_fact_catalog": _fact_catalog(facts),
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        },
    ]


@dataclass
class RetailAgentOrchestratorV2_1:
    client: V2_1ModelClient
    registry: V2_1ToolRegistry

    def run_turn(
        self,
        *,
        session_id: str,
        turn_id: str,
        question: str,
        result_root: str = "results/raw/agent_v2_1_mock",
    ) -> AgentTurnOutcomeV2_1:
        prompts = load_report_boundary_prompts_v2_1()
        raw_responses: list[dict[str, Any]] = []
        response_count = 0
        try:
            response = self.client.complete_json(
                messages=[
                    {
                        "role": "system",
                        "content": prompts.decision_gate.content,
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "phase": "decision",
                                "question": question,
                            },
                            ensure_ascii=False,
                        ),
                    },
                ]
            )
            response_count += 1
            raw_responses.append(_response_raw(response))
            if response.tool_calls or not response.content:
                raise V2_1OrchestrationError(
                    "V2.1决策阶段必须返回非空JSON且不得调用工具"
                )
            decision = parse_decision_v2_1(response.content)
        except (
            DeepSeekClientError,
            DecisionProtocolV2_1Error,
            V2_1OrchestrationError,
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
                stage="decision",
                error=exc,
            )

        if isinstance(decision, ClarificationDecisionV2):
            return AgentTurnOutcomeV2_1(
                status="needs_clarification",
                session_id=session_id,
                turn_id=turn_id,
                original_question=question,
                model_response_count=response_count,
                decision=decision,
                raw_responses=tuple(raw_responses),
            )
        if isinstance(decision, BoundaryDecisionV2):
            return AgentTurnOutcomeV2_1(
                status="boundary",
                session_id=session_id,
                turn_id=turn_id,
                original_question=question,
                model_response_count=response_count,
                decision=decision,
                raw_responses=tuple(raw_responses),
            )

        try:
            validate_explicit_question_constraints(question, decision)
        except RecipeV2_1Error as exc:
            return self._failed(
                session_id=session_id,
                turn_id=turn_id,
                question=question,
                response_count=response_count,
                decision=decision,
                calls=[],
                facts=[],
                raw_responses=raw_responses,
                stage="recipe_intent",
                error=exc,
            )
        return self._run_recipe(
            session_id=session_id,
            turn_id=turn_id,
            question=question,
            decision=decision,
            response_count=response_count,
            raw_responses=raw_responses,
            result_root=result_root,
        )

    def _run_recipe(
        self,
        *,
        session_id: str,
        turn_id: str,
        question: str,
        decision: AnalysisRecipeDecisionV2_1,
        response_count: int,
        raw_responses: list[dict[str, Any]],
        result_root: str,
    ) -> AgentTurnOutcomeV2_1:
        schemas = {
            item["function"]["name"]: item
            for item in self.registry.provider_schemas()
        }
        sequence = RECIPE_TOOL_SEQUENCE_V2_1[
            decision.recipe_id
        ]
        completed: list[str] = []
        calls: list[ExecutedToolCallV2_1] = []
        facts: list[FactRecord] = []
        fact_builder = FactBuilder()

        while len(completed) < len(sequence):
            try:
                step = next_recipe_step(
                    decision,
                    completed_tool_names=completed,
                    current_turn_facts=facts,
                )
                response = self.client.complete_strict_tools(
                    messages=_tool_message(step, facts),
                    tools=[
                        deepseek_strict_tool_schema(
                            schemas[step.tool_name]
                        )
                    ],
                )
                response_count += 1
                raw_responses.append(_response_raw(response))
                if len(response.tool_calls) != 1:
                    raise V2_1OrchestrationError(
                        "每个配方步骤必须且只能返回一个工具调用"
                    )
                provider_call = response.tool_calls[0]
                if provider_call.tool_name != step.tool_name:
                    raise V2_1OrchestrationError(
                        "模型工具名与程序配方步骤不一致"
                    )
                if provider_call.arguments != step.arguments:
                    raise V2_1OrchestrationError(
                        "模型工具参数与程序展开参数不一致"
                    )
                result = self.registry.execute(
                    step.tool_name,
                    step.arguments,
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
                validate_step_facts(step, list(call_facts))
                calls.append(
                    ExecutedToolCallV2_1(
                        call_id=call_id,
                        provider_call_id=(
                            provider_call.provider_call_id
                        ),
                        tool_name=step.tool_name,
                        arguments=step.arguments,
                        result_path=result_path,
                        result=result,
                        facts=call_facts,
                        dependency_fact_ids=(
                            step.dependency_fact_ids
                        ),
                    )
                )
                completed.append(step.tool_name)
                facts.extend(call_facts)
            except (
                DeepSeekClientError,
                RecipeV2_1Error,
                V2_1OrchestrationError,
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
                    stage="recipe_execution",
                    error=exc,
                )

        return self._finalize_report(
            session_id=session_id,
            turn_id=turn_id,
            question=question,
            decision=decision,
            response_count=response_count,
            calls=calls,
            facts=facts,
            raw_responses=raw_responses,
        )

    def _finalize_report(
        self,
        *,
        session_id: str,
        turn_id: str,
        question: str,
        decision: AnalysisRecipeDecisionV2_1,
        response_count: int,
        calls: list[ExecutedToolCallV2_1],
        facts: list[FactRecord],
        raw_responses: list[dict[str, Any]],
    ) -> AgentTurnOutcomeV2_1:
        prompts = load_report_boundary_prompts_v2_1()
        try:
            response = self.client.complete_json(
                messages=[
                    {
                        "role": "system",
                        "content": prompts.report_semantic_planner.content,
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "phase": "semantic_report",
                                "question": question,
                                "session_id": session_id,
                                "turn_id": turn_id,
                                "recipe_id": decision.recipe_id,
                                "fact_catalog": _fact_catalog(facts),
                                "schema": (
                                    SemanticReportPlanV2_1
                                    .model_json_schema()
                                ),
                            },
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                    },
                ]
            )
            response_count += 1
            raw_responses.append(_response_raw(response))
            if response.tool_calls or not response.content:
                raise V2_1OrchestrationError(
                    "语义报告阶段必须返回非空JSON且不得调用工具"
                )
            plan = SemanticReportPlanV2_1.model_validate_json(
                response.content
            )
            if (
                plan.session_id != session_id
                or plan.turn_id != turn_id
                or plan.recipe_id != decision.recipe_id
            ):
                raise V2_1OrchestrationError(
                    "语义报告会话、轮次或配方与当前执行不一致"
                )
            validation = validate_semantic_report_v2_1(
                plan,
                facts,
            )
            if validation.status != "passed":
                codes = "、".join(
                    issue.code for issue in validation.issues
                )
                raise V2_1OrchestrationError(
                    f"语义报告FACT签名校验失败：{codes}"
                )
            markdown = render_semantic_report_v2_1(plan, facts)
        except (
            DeepSeekClientError,
            ValidationError,
            V2_1OrchestrationError,
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
                stage="semantic_report",
                error=exc,
            )
        return AgentTurnOutcomeV2_1(
            status="completed",
            session_id=session_id,
            turn_id=turn_id,
            original_question=question,
            model_response_count=response_count,
            decision=decision,
            tool_calls=tuple(calls),
            facts=tuple(facts),
            report_plan=plan,
            report_validation=validation,
            report_markdown=markdown,
            raw_responses=tuple(raw_responses),
        )

    @staticmethod
    def _failed(
        *,
        session_id: str,
        turn_id: str,
        question: str,
        response_count: int,
        decision: DecisionV2_1 | None,
        calls: list[ExecutedToolCallV2_1],
        facts: list[FactRecord],
        raw_responses: list[dict[str, Any]],
        stage: str,
        error: Exception,
    ) -> AgentTurnOutcomeV2_1:
        return AgentTurnOutcomeV2_1(
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
