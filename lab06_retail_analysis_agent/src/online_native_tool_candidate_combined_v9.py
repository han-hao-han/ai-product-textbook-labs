"""Combined v7 routing with structural report guard v9."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from src.deepseek_client import DeepSeekClientError
from src.online_native_tool_candidate_combined_v8 import (
    NativeToolOnlineCandidateCombinedV8,
)
from src.online_native_tool_candidate_combined_v7 import (
    project_runtime_messages_combined_v7,
)
from src.terminal_structural_guard_v9 import project_terminal_context_v9


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTROL_MESSAGE_GUARD_PATH = (
    PROJECT_ROOT / "prompts" / "native_tool_control_message_guard_v9.md"
)
COMBINED_PROMPT_VERSION = (
    "1.5.6-h3-native-tool-routing-v3-report-v5-structural-guard-v9"
)


def project_runtime_messages_combined_v9(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    projected = project_runtime_messages_combined_v7(messages)
    guard = CONTROL_MESSAGE_GUARD_PATH.read_text(encoding="utf-8").strip()
    replacements = 0
    result: list[dict[str, Any]] = []
    for message in projected:
        copied = dict(message)
        if copied.get("role") == "system" and isinstance(
            copied.get("content"), str
        ):
            copied["content"] = copied["content"].rstrip() + "\n\n" + guard
            replacements += 1
        result.append(copied)
    if replacements != 1:
        raise DeepSeekClientError(
            "combined_v9_projection: exactly one system Prompt is required"
        )
    return result


@dataclass
class NativeToolOnlineCandidateCombinedV9(
    NativeToolOnlineCandidateCombinedV8
):
    runtime_message_projector: Callable[
        [list[dict[str, Any]]], list[dict[str, Any]]
    ] = field(
        init=False,
        default_factory=lambda: project_runtime_messages_combined_v9,
        repr=False,
    )
    terminal_context_projector: Callable[[Any], Any] = field(
        init=False,
        default_factory=lambda: project_terminal_context_v9,
        repr=False,
    )


__all__ = [
    "COMBINED_PROMPT_VERSION",
    "CONTROL_MESSAGE_GUARD_PATH",
    "NativeToolOnlineCandidateCombinedV9",
    "project_runtime_messages_combined_v9",
]
