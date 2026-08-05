"""General native-tool chat runtime decoupled from the fixed-question Harness."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable

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
)
from src.deepseek_provider_schema_adapter_v2_1_revision import (
    DeepSeekProviderSchemaAdapterError,
    adapt_deepseek_provider_schema,
    normalize_deepseek_provider_arguments,
)
from src.native_tool_agent_v2_1_revision import FROZEN_TOOL_NAMES
from src.online_native_tool_candidate_claim_controller_v3_1 import (
    NativeToolOnlineCandidateClaimControllerV3_1,
)
from src.online_native_tool_candidate_v2_3_4_2 import (
    _project_runtime_messages_v2_3_4_2,
)
from src.prompt_contract import load_native_tool_agent_prompts_evidence_guard_v1


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHAT_PROMPT_PATH = PROJECT_ROOT / "prompts" / "native_tool_chat_runtime_v2.md"
CHAT_PROMPT_VERSION = "1.5.6-h4-native-tool-chat-runtime-v2"
CHAT_REAL_MODEL_CONFIRMATION = "I_AUTHORIZE_H4_NATIVE_TOOL_CHAT_REAL_MODEL_CALLS"
MAX_CHAT_MODEL_RESPONSES = 12
MAX_CHAT_TOOL_CALLS = 8


def project_chat_runtime_messages(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    projected = _project_runtime_messages_v2_3_4_2(messages)
    old_system = load_native_tool_agent_prompts_evidence_guard_v1().system.content
    new_system = CHAT_PROMPT_PATH.read_text(encoding="utf-8").strip()
    replacements = 0
    result: list[dict[str, Any]] = []
    for message in projected:
        copied = dict(message)
        content = copied.get("content")
        if copied.get("role") == "system" and isinstance(content, str):
            if old_system not in content:
                raise DeepSeekClientError(
                    "chat_runtime_prompt_projection: frozen system marker missing"
                )
            copied["content"] = content.replace(old_system, new_system, 1)
            replacements += 1
        result.append(copied)
    if replacements != 1:
        raise DeepSeekClientError(
            "chat_runtime_prompt_projection: exactly one system Prompt is required"
        )
    return result


def validate_chat_real_authorization(
    *, confirmation: str, approved_model_responses: int, question_count: int
) -> None:
    if confirmation != CHAT_REAL_MODEL_CONFIRMATION:
        raise ValueError("chat runtime real-model confirmation is missing")
    if (
        isinstance(approved_model_responses, bool)
        or not isinstance(approved_model_responses, int)
        or not 1 <= approved_model_responses <= MAX_CHAT_MODEL_RESPONSES
    ):
        raise ValueError("chat response limit must be between 1 and 12")
    if question_count != 1:
        raise ValueError("chat runtime executes exactly one user-triggered turn")


@dataclass(frozen=True)
class ChatModelStepTrace:
    response_index: int
    action: str
    selected_tool_name: str | None
    selected_arguments: dict[str, Any] | None
    tool_result_messages_seen: int
    requested_tool_choice: str


class GeneralChatClientAdapter:
    """Expose generic native tool selection, then force the V3.1 finalizer."""

    def __init__(self, client: Any) -> None:
        self.client = client
        self.traces: list[ChatModelStepTrace] = []

    @staticmethod
    def _adapt_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        adapted = [adapt_deepseek_provider_schema(item) for item in tools]
        names = tuple(item["function"]["name"] for item in adapted)
        if len(names) != len(set(names)) or set(names) != set(FROZEN_TOOL_NAMES):
            raise DeepSeekClientError(
                "chat runtime must expose exactly the seven frozen tools"
            )
        return adapted

    @staticmethod
    def _tool_payloads(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [item for item in messages if item.get("role") == "tool"]

    @staticmethod
    def _executed_signatures(
        messages: list[dict[str, Any]],
    ) -> set[tuple[str, str]]:
        signatures: set[tuple[str, str]] = set()
        for message in messages:
            if message.get("role") != "tool":
                continue
            try:
                payload = json.loads(message["content"])
                name = str(payload["tool_name"])
                arguments = json.dumps(
                    payload["arguments"],
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue
            signatures.add((name, arguments))
        return signatures

    @staticmethod
    def _signature(call: ProviderToolCall) -> tuple[str, str]:
        return (
            call.tool_name,
            json.dumps(
                call.arguments,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
        )

    @staticmethod
    def _normalize_chat_arguments(
        call: ProviderToolCall,
    ) -> dict[str, Any]:
        arguments = normalize_deepseek_provider_arguments(
            call.tool_name, call.arguments
        )
        if arguments.get("period") in {
            "all_data",
            "complete_months_only",
        }:
            for field_name in ("start_date", "end_date"):
                if arguments.get(field_name) == "null":
                    arguments[field_name] = None
        return arguments

    @staticmethod
    def _normalize(result: ChatCompletionResult) -> ChatCompletionResult:
        if not result.tool_calls:
            return result
        normalized: list[ProviderToolCall] = []
        for call in result.tool_calls:
            try:
                arguments = GeneralChatClientAdapter._normalize_chat_arguments(
                    call
                )
            except DeepSeekProviderSchemaAdapterError:
                raise
            normalized.append(
                ProviderToolCall(
                    provider_call_id=call.provider_call_id,
                    tool_name=call.tool_name,
                    arguments=arguments,
                )
            )
        return replace(
            result,
            tool_calls=tuple(normalized),
        )

    def _trace_tool_call(
        self,
        call: ProviderToolCall,
        *,
        action: str,
        tool_payload_count: int,
    ) -> None:
        self.traces.append(
            ChatModelStepTrace(
                response_index=len(self.traces) + 1,
                action=action,
                selected_tool_name=call.tool_name,
                selected_arguments=dict(call.arguments),
                tool_result_messages_seen=tool_payload_count,
                requested_tool_choice="auto",
            )
        )

    def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ChatCompletionResult:
        adapted = self._adapt_tools(tools)
        tool_payload_count = len(self._tool_payloads(messages))
        route = self.client.complete_strict_tools(
            messages=messages,
            tools=adapted,
            tool_choice="auto",
            response_format=None,
        )
        if route.finish_reason == "length":
            raise TerminalOutputTruncatedError(
                "聊天路由响应达到输出上限"
            )
        route = self._normalize(route)
        if route.tool_calls:
            provider_ids = [call.provider_call_id for call in route.tool_calls]
            if len(provider_ids) != len(set(provider_ids)):
                raise DeepSeekClientError(
                    "聊天路由返回了重复的provider tool call id"
                )
            if len(route.tool_calls) > MAX_CHAT_TOOL_CALLS:
                raise DeepSeekClientError(
                    "聊天路由单次返回的工具调用超过本轮八次上限"
                )
            executed = self._executed_signatures(messages)
            candidates = [
                call
                for call in route.tool_calls
                if self._signature(call) not in executed
            ]
            if not candidates:
                raise DeepSeekClientError(
                    "聊天路由只返回了已经执行过的相同工具和参数"
                )
            first = candidates[0]
            self._trace_tool_call(
                first,
                action=(
                    "batched_tool_calls_replanned"
                    if len(route.tool_calls) > 1
                    else "tool_call"
                ),
                tool_payload_count=tool_payload_count,
            )
            route = replace(route, tool_calls=(first,))
        else:
            self.traces.append(
                ChatModelStepTrace(
                    response_index=len(self.traces) + 1,
                    action="control_response",
                    selected_tool_name=None,
                    selected_arguments=None,
                    tool_result_messages_seen=tool_payload_count,
                    requested_tool_choice="auto",
                )
            )
        if route.tool_calls or tool_payload_count == 0:
            return route

        final = self.client.complete_strict_tools(
            messages=messages,
            tools=adapted,
            tool_choice="none",
            response_format={"type": "json_object"},
        )
        if final.finish_reason == "length":
            raise TerminalOutputTruncatedError(
                "聊天报告终态响应达到输出上限"
            )
        self.traces.append(
            ChatModelStepTrace(
                response_index=len(self.traces) + 1,
                action="v3_1_report_finalized",
                selected_tool_name=None,
                selected_arguments=None,
                tool_result_messages_seen=tool_payload_count,
                requested_tool_choice="none",
            )
        )
        return final


@dataclass
class NativeToolChatRuntimeV1(
    NativeToolOnlineCandidateClaimControllerV3_1
):
    runtime_message_projector: Callable[
        [list[dict[str, Any]]], list[dict[str, Any]]
    ] = field(
        init=False,
        default_factory=lambda: project_chat_runtime_messages,
        repr=False,
    )
    real_authorization_validator: Callable[..., None] = field(
        init=False,
        default_factory=lambda: validate_chat_real_authorization,
        repr=False,
    )
    chat_trace: tuple[ChatModelStepTrace, ...] = field(
        init=False, default=()
    )

    def run_chat_turn(
        self,
        *,
        session_id: str,
        turn_id: str,
        question: str,
        clarification_count: int = 0,
        clarification_answer: str | None = None,
        result_root: str,
    ) -> AgentTurnOutcome:
        adapter = GeneralChatClientAdapter(self.client)
        outcome = RetailAgentOrchestrator(
            client=adapter,
            registry=self.registry,
            prompts=load_native_tool_agent_prompts_evidence_guard_v1(),
            max_tool_calls_per_turn=MAX_CHAT_TOOL_CALLS,
        ).run_turn(
            session_id=session_id,
            turn_id=turn_id,
            question=question,
            clarification_count=clarification_count,
            clarification_answer=clarification_answer,
            result_root=result_root,
        )
        raw_responses = tuple(getattr(self.client, "raw_responses", ()))
        snapshot = self.response_limiter.snapshot()
        if raw_responses:
            outcome = replace(
                outcome,
                model_response_count=snapshot.attempted,
                raw_responses=raw_responses,
            )
        self.chat_trace = tuple(adapter.traces)
        self.atom_selection_trace = tuple(self.client.selection_traces)
        self.terminal_protocol_trace = tuple(
            self.client.terminal_protocol_traces
        )
        return outcome


__all__ = [
    "CHAT_PROMPT_PATH", "CHAT_PROMPT_VERSION", "CHAT_REAL_MODEL_CONFIRMATION",
    "ChatModelStepTrace", "GeneralChatClientAdapter", "MAX_CHAT_MODEL_RESPONSES",
    "MAX_CHAT_TOOL_CALLS",
    "NativeToolChatRuntimeV1", "project_chat_runtime_messages",
    "validate_chat_real_authorization",
]
