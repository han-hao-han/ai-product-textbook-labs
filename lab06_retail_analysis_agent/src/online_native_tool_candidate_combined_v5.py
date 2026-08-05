"""Tool-routing v3 plus report evidence Prompt v5."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from src.deepseek_client import DeepSeekClientError
from src.online_native_tool_candidate_combined_v4 import (
    NativeToolOnlineCandidateCombinedV4,
    REPORT_PROMPT_PATH as REPORT_V4_PATH,
    project_runtime_messages_combined_v4,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMBINED_PROMPT_VERSION = "1.5.6-h3-native-tool-routing-v3-report-v5"
REPORT_PROMPT_PATH = (
    PROJECT_ROOT / "prompts" / "native_tool_report_metric_binding_v5.md"
)


def project_runtime_messages_combined_v5(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    projected = project_runtime_messages_combined_v4(messages)
    report_v4 = REPORT_V4_PATH.read_text(encoding="utf-8").strip()
    report_v5 = REPORT_PROMPT_PATH.read_text(encoding="utf-8").strip()
    replacements = 0
    result: list[dict[str, Any]] = []
    for message in projected:
        copied = dict(message)
        content = copied.get("content")
        if copied.get("role") == "system" and isinstance(content, str):
            if report_v4 not in content:
                raise DeepSeekClientError(
                    "combined_v5_projection: report v4 marker missing"
                )
            copied["content"] = content.replace(report_v4, report_v5, 1)
            replacements += 1
        result.append(copied)
    if replacements != 1:
        raise DeepSeekClientError(
            "combined_v5_projection: exactly one system Prompt is required"
        )
    return result


@dataclass
class NativeToolOnlineCandidateCombinedV5(
    NativeToolOnlineCandidateCombinedV4
):
    runtime_message_projector: Callable[
        [list[dict[str, Any]]], list[dict[str, Any]]
    ] = field(
        init=False,
        default_factory=lambda: project_runtime_messages_combined_v5,
        repr=False,
    )


__all__ = [
    "COMBINED_PROMPT_VERSION",
    "NativeToolOnlineCandidateCombinedV5",
    "REPORT_PROMPT_PATH",
    "project_runtime_messages_combined_v5",
]
