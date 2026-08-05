"""Combined v5 with v7 argument and summary-coverage guidance."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from src.deepseek_client import DeepSeekClientError
from src.online_native_tool_candidate_combined_v6 import (
    NativeToolOnlineCandidateCombinedV6,
)
from src.online_native_tool_candidate_combined_v5 import (
    project_runtime_messages_combined_v5,
)
from src.terminal_summary_coverage_v7 import project_terminal_context_v7


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ARGUMENT_GUARD_PATH = (
    PROJECT_ROOT / "prompts" / "native_tool_argument_json_guard_v7.md"
)
COMBINED_PROMPT_VERSION = (
    "1.5.6-h3-native-tool-routing-v3-report-v5-summary-coverage-v7"
)


def project_runtime_messages_combined_v7(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    projected = project_runtime_messages_combined_v5(messages)
    guard = ARGUMENT_GUARD_PATH.read_text(encoding="utf-8").strip()
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
            "combined_v7_projection: exactly one system Prompt is required"
        )
    return result


@dataclass
class NativeToolOnlineCandidateCombinedV7(
    NativeToolOnlineCandidateCombinedV6
):
    runtime_message_projector: Callable[
        [list[dict[str, Any]]], list[dict[str, Any]]
    ] = field(
        init=False,
        default_factory=lambda: project_runtime_messages_combined_v7,
        repr=False,
    )
    terminal_context_projector: Callable[[Any], Any] = field(
        init=False,
        default_factory=lambda: project_terminal_context_v7,
        repr=False,
    )


__all__ = [
    "ARGUMENT_GUARD_PATH",
    "COMBINED_PROMPT_VERSION",
    "NativeToolOnlineCandidateCombinedV7",
    "project_runtime_messages_combined_v7",
]
