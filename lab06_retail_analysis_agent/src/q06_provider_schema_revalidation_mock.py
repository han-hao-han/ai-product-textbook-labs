"""Provider-shaped Q06 mock for the schema-adapter revalidation plan."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.deepseek_client import ChatCompletionResult, ProviderToolCall
from src.deepseek_provider_schema_adapter_v2_1_revision import (
    DEEPSEEK_NONE_SENTINEL,
)
from src.mock_native_tool_client_v2_1_revision import (
    FrozenQuestionNativeToolMockClient,
)


@dataclass
class Q06ProviderSchemaRevalidationMockClient:
    """Emit the exact provider sentinel on Q06's first response."""

    delegate: FrozenQuestionNativeToolMockClient = field(
        default_factory=FrozenQuestionNativeToolMockClient
    )

    def complete_strict_tools(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: str = "auto",
    ) -> ChatCompletionResult:
        result = self.delegate.complete_strict_tools(
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
        )
        if not result.tool_calls:
            return result
        selected = result.tool_calls[0]
        if selected.tool_name != "analyze_time_trend":
            return result
        provider_arguments = dict(selected.arguments)
        provider_arguments["start_date"] = DEEPSEEK_NONE_SENTINEL
        provider_arguments["end_date"] = DEEPSEEK_NONE_SENTINEL
        return ChatCompletionResult(
            finish_reason=result.finish_reason,
            content=result.content,
            tool_calls=(
                ProviderToolCall(
                    provider_call_id=selected.provider_call_id,
                    tool_name=selected.tool_name,
                    arguments=provider_arguments,
                ),
            ),
            raw_response={
                **result.raw_response,
                "provider_schema_revalidation_mock": True,
            },
            usage=result.usage,
        )
