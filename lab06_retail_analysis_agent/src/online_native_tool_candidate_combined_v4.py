"""Tool-routing v3 plus report evidence Prompt v4."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from src.deepseek_client import DeepSeekClientError
from src.online_native_tool_candidate_combined_v3 import (
    NativeToolOnlineCandidateCombinedV3,
    REPORT_PROMPT_PATH as REPORT_V3_PATH,
    project_runtime_messages_combined_v3,
)
from src.online_native_tool_candidate_tool_routing_v2 import (
    TOOL_ROUTING_PROMPT_PATH as TOOL_ROUTING_V2_PATH,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMBINED_PROMPT_VERSION = "1.5.6-h3-native-tool-routing-v3-report-v4"
TOOL_ROUTING_PROMPT_PATH = (
    PROJECT_ROOT / "prompts" / "native_tool_agent_system_tool_routing_v3.md"
)
REPORT_PROMPT_PATH = (
    PROJECT_ROOT / "prompts" / "native_tool_report_metric_binding_v4.md"
)


def project_runtime_messages_combined_v4(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    projected = project_runtime_messages_combined_v3(messages)
    tool_v2 = TOOL_ROUTING_V2_PATH.read_text(encoding="utf-8").strip()
    tool_v3 = TOOL_ROUTING_PROMPT_PATH.read_text(encoding="utf-8").strip()
    report_v3 = REPORT_V3_PATH.read_text(encoding="utf-8").strip()
    report_v4 = REPORT_PROMPT_PATH.read_text(encoding="utf-8").strip()
    replacements = 0
    result: list[dict[str, Any]] = []
    for message in projected:
        copied = dict(message)
        content = copied.get("content")
        if copied.get("role") == "system" and isinstance(content, str):
            if tool_v2 not in content or report_v3 not in content:
                raise DeepSeekClientError(
                    "combined_v4_projection: predecessor Prompt marker missing"
                )
            copied["content"] = content.replace(tool_v2, tool_v3, 1).replace(
                report_v3, report_v4, 1
            )
            replacements += 1
        result.append(copied)
    if replacements != 1:
        raise DeepSeekClientError(
            "combined_v4_projection: exactly one system Prompt is required"
        )
    return result


@dataclass
class NativeToolOnlineCandidateCombinedV4(
    NativeToolOnlineCandidateCombinedV3
):
    runtime_message_projector: Callable[
        [list[dict[str, Any]]], list[dict[str, Any]]
    ] = field(
        init=False,
        default_factory=lambda: project_runtime_messages_combined_v4,
        repr=False,
    )


__all__ = [
    "COMBINED_PROMPT_VERSION",
    "NativeToolOnlineCandidateCombinedV4",
    "REPORT_PROMPT_PATH",
    "TOOL_ROUTING_PROMPT_PATH",
    "project_runtime_messages_combined_v4",
]
