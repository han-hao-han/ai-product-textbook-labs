"""Offline model double that reproduces the observed Q06 terminal conflict."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.deepseek_client import ChatCompletionResult, ProviderToolCall
from src.mock_native_tool_client_v2_1_revision import (
    FrozenQuestionNativeToolMockClient,
)


@dataclass
class Q06ReportTerminalConflictMockClient:
    """Call an extra tool under ``auto`` but report under ``none``.

    The first two responses are delegated to the frozen Q06 mock.  On the
    third response this double mirrors both observed real runs: its text says
    the evidence is complete while ``tool_choice=auto`` still permits an
    unnecessary ``get_data_profile`` call.  ``tool_choice=none`` returns the
    same frozen FACT-grounded report as the delegate.
    """

    delegate: FrozenQuestionNativeToolMockClient = field(
        default_factory=FrozenQuestionNativeToolMockClient
    )

    def complete_strict_tools(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: str = "auto",
        response_format: dict[str, str] | None = None,
    ) -> ChatCompletionResult:
        tool_result_count = sum(
            message.get("role") == "tool" for message in messages
        )
        if tool_result_count == 2 and tool_choice == "auto":
            return ChatCompletionResult(
                finish_reason="tool_calls",
                content=(
                    "The evidence is complete. I will now generate the final "
                    "report."
                ),
                tool_calls=(
                    ProviderToolCall(
                        provider_call_id="offline-terminal-conflict",
                        tool_name="get_data_profile",
                        arguments={"section": "summary"},
                    ),
                ),
                raw_response={
                    "offline_mock": True,
                    "phase": "legacy_auto_terminal_conflict",
                    "model": "deepseek-v4-flash",
                    "usage": {
                        "prompt_tokens": 100,
                        "completion_tokens": 20,
                        "total_tokens": 120,
                    },
                },
                usage={
                    "prompt_tokens": 100,
                    "completion_tokens": 20,
                    "total_tokens": 120,
                },
            )
        return self.delegate.complete_strict_tools(
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
            response_format=response_format,
        )
