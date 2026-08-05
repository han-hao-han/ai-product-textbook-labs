"""Tool-routing v2 plus claim-local metric-binding report Prompt v3."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from src.deepseek_client import DeepSeekClientError
from src.online_native_tool_candidate_tool_routing_v2 import (
    NativeToolOnlineCandidateToolRoutingV2,
    project_runtime_messages_tool_routing_v2,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMBINED_PROMPT_VERSION = "1.5.6-h3-native-tool-routing-v2-report-v3"
REPORT_PREDECESSOR_PATH = (
    PROJECT_ROOT / "prompts" / "native_tool_report_internal_source_v2_3_4_2.md"
)
REPORT_PROMPT_PATH = (
    PROJECT_ROOT / "prompts" / "native_tool_report_metric_binding_v3.md"
)


def project_runtime_messages_combined_v3(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    projected = project_runtime_messages_tool_routing_v2(messages)
    predecessor = REPORT_PREDECESSOR_PATH.read_text(encoding="utf-8").strip()
    candidate = REPORT_PROMPT_PATH.read_text(encoding="utf-8").strip()
    replacements = 0
    result: list[dict[str, Any]] = []
    for message in projected:
        copied = dict(message)
        content = copied.get("content")
        if copied.get("role") == "system" and isinstance(content, str):
            if predecessor not in content:
                raise DeepSeekClientError(
                    "combined_v3_projection: report Prompt marker missing"
                )
            copied["content"] = content.replace(predecessor, candidate, 1)
            replacements += 1
        result.append(copied)
    if replacements != 1:
        raise DeepSeekClientError(
            "combined_v3_projection: exactly one report Prompt is required"
        )
    return result


@dataclass
class NativeToolOnlineCandidateCombinedV3(
    NativeToolOnlineCandidateToolRoutingV2
):
    runtime_message_projector: Callable[
        [list[dict[str, Any]]], list[dict[str, Any]]
    ] = field(
        init=False,
        default_factory=lambda: project_runtime_messages_combined_v3,
        repr=False,
    )


__all__ = [
    "COMBINED_PROMPT_VERSION",
    "NativeToolOnlineCandidateCombinedV3",
    "REPORT_PROMPT_PATH",
    "project_runtime_messages_combined_v3",
]
