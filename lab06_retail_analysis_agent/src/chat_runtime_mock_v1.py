"""Scripted offline model double for the general H4 chat runtime."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from src.claim_level_report_controller_mock_v3_1 import (
    ClaimTemplateLogicalClientV3_1,
)
from src.deepseek_client import ChatCompletionResult, ProviderToolCall
from src.mock_native_tool_client_v2_1_revision import _result


StepArguments = dict[str, Any] | Callable[[list[dict[str, Any]]], dict[str, Any]]


@dataclass
class ScriptedChatRoutingClient:
    steps: list[tuple[str, StepArguments]]
    require_clarification: bool = False
    batch_first_response: bool = False
    repeat_batch_while_incomplete: bool = False
    call_count: int = 0

    @staticmethod
    def _tool_payloads(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            json.loads(item["content"])
            for item in messages
            if item.get("role") == "tool"
        ]

    def complete_strict_tools(self, **kwargs: Any) -> ChatCompletionResult:
        messages = kwargs["messages"]
        payloads = self._tool_payloads(messages)
        has_answer = any(
            item.get("role") == "user"
            and isinstance(item.get("content"), str)
            and item["content"].startswith("对集中澄清问题的回答：")
            for item in messages
        )
        if self.require_clarification and not has_answer and not payloads:
            return _result(
                content=json.dumps(
                    {
                        "response_type": "clarification",
                        "message": "请一次补充时间范围、核心指标以及比较维度或对象。",
                        "topics": [
                            "time_range",
                            "metric",
                            "comparison_dimension_or_objects",
                        ],
                    },
                    ensure_ascii=False,
                )
            )
        should_batch = self.steps and (
            (self.batch_first_response and not payloads)
            or (
                self.repeat_batch_while_incomplete
                and len(payloads) < len(self.steps)
            )
        )
        if should_batch:
            calls: list[ProviderToolCall] = []
            for tool_name, raw_arguments in self.steps:
                arguments = (
                    raw_arguments(payloads)
                    if callable(raw_arguments)
                    else dict(raw_arguments)
                )
                self.call_count += 1
                calls.append(
                    ProviderToolCall(
                        provider_call_id=f"provider-call-{self.call_count:03d}",
                        tool_name=tool_name,
                        arguments=arguments,
                    )
                )
            return ChatCompletionResult(
                finish_reason="tool_calls",
                content=None,
                tool_calls=tuple(calls),
                raw_response={"mock": "batched_tool_calls"},
                usage=None,
            )
        if len(payloads) < len(self.steps):
            tool_name, raw_arguments = self.steps[len(payloads)]
            arguments = (
                raw_arguments(payloads)
                if callable(raw_arguments)
                else dict(raw_arguments)
            )
            self.call_count += 1
            return _result(
                tool_name=tool_name,
                arguments=arguments,
                call_index=self.call_count,
            )
        return _result(content='{"response_type":"analysis_complete"}')


@dataclass
class ChatRuntimeLogicalClientV1(ClaimTemplateLogicalClientV3_1):
    delegate: ScriptedChatRoutingClient = field(default_factory=lambda: ScriptedChatRoutingClient([]))


__all__ = ["ChatRuntimeLogicalClientV1", "ScriptedChatRoutingClient"]
