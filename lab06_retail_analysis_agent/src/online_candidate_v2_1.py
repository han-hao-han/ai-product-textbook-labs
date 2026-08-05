"""Safety boundary shared by the V2.1 online candidate and offline transport tests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.deepseek_client import (
    ChatCompletionResult,
    DeepSeekClientError,
)


REAL_MODEL_CONFIRMATION_V2_1 = "I_AUTHORIZE_V2_1_REAL_MODEL_CALLS"
MAX_RESPONSES_PER_FIXED_QUESTION = 4


@dataclass(frozen=True)
class ResponseLimitSnapshotV2_1:
    limit: int
    attempted: int
    completed: int
    failed: int


class ResponseLimitedClientV2_1:
    """Reserve one approved response before every transport attempt."""

    def __init__(self, client: Any, *, limit: int) -> None:
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError("模型响应上限必须是整数")
        if limit <= 0:
            raise ValueError("模型响应上限必须大于0")
        self.client = client
        self.limit = limit
        self.attempted = 0
        self.completed = 0
        self.failed = 0

    def _reserve(self) -> None:
        if self.attempted >= self.limit:
            raise DeepSeekClientError(
                "已达到命令行明确批准的V2.1模型响应上限"
            )
        self.attempted += 1

    def _complete(self, operation: Any) -> ChatCompletionResult:
        self._reserve()
        try:
            result = operation()
        except Exception:
            self.failed += 1
            raise
        self.completed += 1
        return result

    def complete_json(
        self,
        *,
        messages: list[dict[str, Any]],
    ) -> ChatCompletionResult:
        return self._complete(
            lambda: self.client.complete_json(messages=messages)
        )

    def complete_strict_tools(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ChatCompletionResult:
        return self._complete(
            lambda: self.client.complete_strict_tools(
                messages=messages,
                tools=tools,
            )
        )

    def snapshot(self) -> ResponseLimitSnapshotV2_1:
        return ResponseLimitSnapshotV2_1(
            limit=self.limit,
            attempted=self.attempted,
            completed=self.completed,
            failed=self.failed,
        )


def validate_real_model_authorization_v2_1(
    *,
    confirmation: str,
    approved_model_responses: int,
    question_count: int,
) -> None:
    """Reject accidental or over-broad online candidate execution."""

    if confirmation != REAL_MODEL_CONFIRMATION_V2_1:
        raise ValueError("未提供V2.1真实模型调用确认文本")
    if (
        isinstance(approved_model_responses, bool)
        or not isinstance(approved_model_responses, int)
        or approved_model_responses <= 0
    ):
        raise ValueError("批准的模型响应上限必须是正整数")
    if (
        isinstance(question_count, bool)
        or not isinstance(question_count, int)
        or question_count <= 0
    ):
        raise ValueError("固定问题数量必须是正整数")
    maximum = question_count * MAX_RESPONSES_PER_FIXED_QUESTION
    if approved_model_responses > maximum:
        raise ValueError(
            "批准的模型响应上限超过所选固定问题的程序级最大值"
        )
