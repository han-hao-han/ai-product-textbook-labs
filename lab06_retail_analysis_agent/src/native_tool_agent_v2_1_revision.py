"""Independent native-tool entry for the corrected V2.1 mainline.

The model always receives the complete frozen whitelist.  This module does
not import recipe routing or program-generated tool plans.
"""

from __future__ import annotations

import calendar
import json
from dataclasses import dataclass, field, replace
from typing import Any, Protocol

from src.agent_orchestrator import (
    AgentOrchestrationError,
    AgentTurnOutcome,
    RetailAgentOrchestrator,
)
from src.deepseek_client import (
    ChatCompletionResult,
    DeepSeekClientError,
    ProviderToolCall,
    TerminalOutputTruncatedError,
    strict_tool_request_max_tokens,
)
from src.deepseek_provider_schema_adapter_v2_1_revision import (
    DeepSeekProviderSchemaAdapterError,
    adapt_deepseek_provider_schema,
    normalize_deepseek_provider_arguments,
)
from src.prompt_contract import (
    AgentPromptBundle,
    load_native_tool_agent_prompts_evidence_guard_v1,
)
from src.fixed_question_validation import load_frozen_questions
from src.tool_registry import ToolExecutionError
from src.tool_schemas import TOOL_ARGUMENT_MODELS


FROZEN_TOOL_NAMES = tuple(TOOL_ARGUMENT_MODELS)
FIXED_TOOL_SEQUENCES = {
    "Q01": ("get_sales_overview",),
    "Q02": ("rank_products",),
    "Q03": ("analyze_regions",),
    "Q04": ("analyze_time_trend",),
    "Q05": ("get_sales_overview", "compare_segments"),
    "Q06": ("analyze_time_trend", "rank_products"),
    "Q07": ("get_sales_overview", "analyze_customers"),
    "Q08": (),
    "Q09": (),
    "Q10": (),
}


class StrictNativeToolClient(Protocol):
    def complete_strict_tools(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: str = "auto",
        response_format: dict[str, str] | None = None,
    ) -> ChatCompletionResult: ...


class NativeToolRegistry(Protocol):
    names: tuple[str, ...]

    def provider_schemas(self) -> list[dict[str, Any]]: ...

    def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class NativeModelStepTrace:
    response_index: int
    visible_tool_names: tuple[str, ...]
    action: str
    selected_tool_name: str | None
    selected_arguments: dict[str, Any] | None
    normalized_arguments: dict[str, Any] | None
    tool_result_messages_seen: int
    requested_tool_choice: str
    requested_response_format: dict[str, str] | None
    requested_max_tokens: int
    finish_reason: str


@dataclass
class _StrictNativeClientAdapter:
    client: StrictNativeToolClient
    q06_terminal_lock_enabled: bool = True
    q06_terminal_json_enabled: bool = True
    terminal_lock_question_ids: tuple[str, ...] | None = None
    terminal_json_question_ids: tuple[str, ...] | None = None
    traces: list[NativeModelStepTrace] = field(default_factory=list)
    observed_raw_responses: list[dict[str, Any]] = field(default_factory=list)

    def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ChatCompletionResult:
        adapted = [adapt_deepseek_provider_schema(item) for item in tools]
        names = tuple(item["function"]["name"] for item in adapted)
        if len(names) != len(set(names)) or set(names) != set(
            FROZEN_TOOL_NAMES
        ):
            raise DeepSeekClientError(
                "native-tool turn must expose exactly the seven frozen tools"
            )
        if any(
            item.get("function", {}).get("strict") is not True
            for item in adapted
        ):
            raise DeepSeekClientError(
                "every native-tool schema must enable strict mode"
            )

        requested_tool_choice = self._requested_tool_choice(messages)
        requested_response_format = self._requested_response_format(
            messages,
            requested_tool_choice=requested_tool_choice,
        )
        request_arguments: dict[str, Any] = {
            "messages": messages,
            "tools": adapted,
            "tool_choice": requested_tool_choice,
        }
        if requested_response_format is not None:
            request_arguments["response_format"] = requested_response_format
        provider_result = self.client.complete_strict_tools(
            **request_arguments,
        )
        self.observed_raw_responses.append(provider_result.raw_response)
        result = provider_result
        normalization_error: DeepSeekProviderSchemaAdapterError | None = None
        normalized_arguments: dict[str, Any] | None = None
        if len(provider_result.tool_calls) == 1:
            provider_call = provider_result.tool_calls[0]
            try:
                normalized_arguments = normalize_deepseek_provider_arguments(
                    provider_call.tool_name,
                    provider_call.arguments,
                )
            except DeepSeekProviderSchemaAdapterError as exc:
                normalization_error = exc
            else:
                result = replace(
                    provider_result,
                    tool_calls=(
                        ProviderToolCall(
                            provider_call_id=provider_call.provider_call_id,
                            tool_name=provider_call.tool_name,
                            arguments=normalized_arguments,
                        ),
                    ),
                )

        if len(provider_result.tool_calls) > 1:
            action = "invalid_multiple_tool_calls"
            selected_name = None
            selected_arguments = None
        elif provider_result.tool_calls:
            selected = provider_result.tool_calls[0]
            action = (
                "invalid_provider_arguments"
                if normalization_error is not None
                else "tool_call"
            )
            selected_name = selected.tool_name
            selected_arguments = dict(selected.arguments)
        else:
            action = "control_response"
            selected_name = None
            selected_arguments = None
        if provider_result.finish_reason == "length":
            action = "truncated_response"
        self.traces.append(
            NativeModelStepTrace(
                response_index=len(self.traces) + 1,
                visible_tool_names=names,
                action=action,
                selected_tool_name=selected_name,
                selected_arguments=selected_arguments,
                normalized_arguments=normalized_arguments,
                tool_result_messages_seen=sum(
                    message.get("role") == "tool" for message in messages
                ),
                requested_tool_choice=requested_tool_choice,
                requested_response_format=requested_response_format,
                requested_max_tokens=strict_tool_request_max_tokens(
                    messages=messages,
                    tool_choice=requested_tool_choice,
                    response_format=requested_response_format,
                ),
                finish_reason=provider_result.finish_reason,
            )
        )
        if provider_result.finish_reason == "length":
            raise TerminalOutputTruncatedError(
                "模型终态响应达到输出上限，JSON可能不完整"
            )
        if normalization_error is not None:
            raise normalization_error
        self._validate_post_choice(messages, result)
        return result

    def _requested_tool_choice(
        self,
        messages: list[dict[str, Any]],
    ) -> str:
        """Lock configured terminal responses after exact evidence chains."""
        question_id = self._fixed_question_id(messages)
        executed = self._executed_payloads(messages)
        lock_ids = (
            set(self.terminal_lock_question_ids)
            if self.terminal_lock_question_ids is not None
            else ({"Q06"} if self.q06_terminal_lock_enabled else set())
        )
        if (
            question_id in lock_ids
            and len(executed) == len(FIXED_TOOL_SEQUENCES[question_id])
            and tuple(item.get("tool_name") for item in executed)
            == FIXED_TOOL_SEQUENCES[question_id]
        ):
            return "none"
        return "auto"

    def _requested_response_format(
        self,
        messages: list[dict[str, Any]],
        *,
        requested_tool_choice: str,
    ) -> dict[str, str] | None:
        """Add JSON mode only to configured locked terminal responses."""
        question_id = self._fixed_question_id(messages)
        json_ids = (
            set(self.terminal_json_question_ids)
            if self.terminal_json_question_ids is not None
            else ({"Q06"} if self.q06_terminal_json_enabled else set())
        )
        if requested_tool_choice == "none" and question_id in json_ids:
            return {"type": "json_object"}
        return None

    @staticmethod
    def _fixed_question_id(
        messages: list[dict[str, Any]],
    ) -> str | None:
        question_by_text = {
            item["question"]: question_id
            for question_id, item in load_frozen_questions().items()
        }
        first_user = next(
            (
                message.get("content")
                for message in messages
                if message.get("role") == "user"
            ),
            None,
        )
        return question_by_text.get(first_user)

    @staticmethod
    def _executed_payloads(
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return [
            json.loads(message["content"])
            for message in messages
            if message.get("role") == "tool"
        ]

    def _validate_post_choice(
        self,
        messages: list[dict[str, Any]],
        result: ChatCompletionResult,
    ) -> None:
        """Validate model choices without selecting or repairing them."""
        executed = self._executed_payloads(messages)
        if result.tool_calls:
            selected = result.tool_calls[0]
            if any(
                item["tool_name"] == selected.tool_name
                and item["arguments"] == selected.arguments
                for item in executed
            ):
                raise AgentOrchestrationError(
                    "duplicate native tool call with identical arguments"
                )

        question_id = self._fixed_question_id(messages)
        if question_id is None:
            return
        expected = FIXED_TOOL_SEQUENCES[question_id]
        next_index = len(executed)
        if result.tool_calls:
            if next_index >= len(expected):
                raise AgentOrchestrationError(
                    f"{question_id} does not allow another tool call"
                )
            selected = result.tool_calls[0]
            if selected.tool_name != expected[next_index]:
                raise AgentOrchestrationError(
                    f"{question_id} model selected an unsupported tool sequence"
                )
            self._validate_fixed_arguments(
                question_id,
                next_index,
                selected.arguments,
                executed,
            )
            return
        if next_index < len(expected):
            raise AgentOrchestrationError(
                f"{question_id} ended before required tool evidence was complete"
            )

    @staticmethod
    def _validate_fixed_arguments(
        question_id: str,
        step_index: int,
        arguments: dict[str, Any],
        executed: list[dict[str, Any]],
    ) -> None:
        expected_subset: dict[str, Any] = {}
        if question_id in {"Q01", "Q05", "Q07"} and step_index == 0:
            expected_subset = {
                "period": "all_data",
                "include_incomplete_period_warning": True,
            }
        elif question_id == "Q02":
            expected_subset = {
                "period": "all_data",
                "metric": "sales_amount",
                "top_n": 5,
            }
        elif question_id == "Q03":
            expected_subset = {
                "period": "all_data",
                "metric": "sales_amount",
                "top_n": 5,
                "excluded_country": "United Kingdom",
            }
        elif question_id in {"Q04", "Q06"} and step_index == 0:
            expected_subset = {
                "period": "complete_months_only",
                "grain": "month",
                "metric": "sales_amount",
                "exclude_incomplete_periods": True,
            }
        elif question_id == "Q05" and step_index == 1:
            expected_subset = {
                "period": "all_data",
                "comparison": "united_kingdom_vs_other",
            }
        elif question_id == "Q07" and step_index == 1:
            expected_subset = {
                "period": "all_data",
                "include_coverage": True,
            }
        elif question_id == "Q06" and step_index == 1:
            facts = [
                fact
                for item in executed
                for fact in item.get("facts", [])
            ]
            peak = next(
                (
                    fact["value"]
                    for fact in facts
                    if fact.get("metric") == "peak_period"
                ),
                None,
            )
            if peak is None:
                raise AgentOrchestrationError(
                    "Q06 second call requires peak_period FACT"
                )
            year, month = map(int, peak.split("-"))
            last_day = calendar.monthrange(year, month)[1]
            expected_subset = {
                "period": "custom",
                "start_date": f"{peak}-01",
                "end_date": f"{peak}-{last_day:02d}",
                "metric": "sales_amount",
                "top_n": 3,
            }
        mismatches = {
            key: (value, arguments.get(key))
            for key, value in expected_subset.items()
            if arguments.get(key) != value
        }
        if mismatches:
            raise AgentOrchestrationError(
                f"{question_id} model arguments violate frozen semantics: "
                f"{mismatches}"
            )


@dataclass
class _RegistryAdapter:
    registry: NativeToolRegistry

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(self.registry.names)

    def provider_schemas(self) -> list[dict[str, Any]]:
        return self.registry.provider_schemas()

    def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            return self.registry.execute(tool_name, arguments)
        except ToolExecutionError:
            raise
        except ValueError as exc:
            raise ToolExecutionError(str(exc)) from exc


@dataclass
class RetailNativeToolAgentV2_1Revision:
    """Facade that exposes only the corrected native-tool mainline."""

    client: StrictNativeToolClient
    registry: NativeToolRegistry
    prompts: AgentPromptBundle = field(
        default_factory=load_native_tool_agent_prompts_evidence_guard_v1
    )
    last_trace: tuple[NativeModelStepTrace, ...] = field(
        init=False,
        default=(),
    )
    q06_terminal_lock_enabled: bool = True
    q06_terminal_json_enabled: bool = True
    terminal_lock_question_ids: tuple[str, ...] | None = None
    terminal_json_question_ids: tuple[str, ...] | None = None

    def run_turn(
        self,
        *,
        session_id: str,
        turn_id: str,
        question: str,
        clarification_count: int = 0,
        clarification_answer: str | None = None,
        result_root: str = "results/raw/native_tool_mock",
    ) -> AgentTurnOutcome:
        adapter = _StrictNativeClientAdapter(
            self.client,
            q06_terminal_lock_enabled=self.q06_terminal_lock_enabled,
            q06_terminal_json_enabled=self.q06_terminal_json_enabled,
            terminal_lock_question_ids=self.terminal_lock_question_ids,
            terminal_json_question_ids=self.terminal_json_question_ids,
        )
        outcome = RetailAgentOrchestrator(
            client=adapter,
            registry=_RegistryAdapter(self.registry),
            prompts=self.prompts,
        ).run_turn(
            session_id=session_id,
            turn_id=turn_id,
            question=question,
            clarification_count=clarification_count,
            clarification_answer=clarification_answer,
            result_root=result_root,
        )
        if len(outcome.raw_responses) < len(adapter.observed_raw_responses):
            outcome = replace(
                outcome,
                model_response_count=len(adapter.observed_raw_responses),
                raw_responses=tuple(adapter.observed_raw_responses),
            )
        self.last_trace = tuple(adapter.traces)
        return outcome
