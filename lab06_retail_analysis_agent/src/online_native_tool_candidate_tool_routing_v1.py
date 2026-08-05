"""V2.3.4.2 protocol candidate with the versioned tool-routing Prompt."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from src.deepseek_client import DeepSeekClientError
from src.online_native_tool_candidate_v2_3_4_2 import (
    NativeToolOnlineCandidateV2_3_4_2,
    _project_runtime_messages_v2_3_4_2,
)
from src.prompt_contract import load_native_tool_agent_prompts_evidence_guard_v1


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOOL_ROUTING_PROMPT_VERSION = "1.5.6-h3-native-tool-routing-v1"
TOOL_ROUTING_PROMPT_PATH = (
    PROJECT_ROOT / "prompts" / "native_tool_agent_system_tool_routing_v1.md"
)


def project_runtime_messages_tool_routing_v1(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    projected = _project_runtime_messages_v2_3_4_2(messages)
    old_system = load_native_tool_agent_prompts_evidence_guard_v1().system.content
    new_system = TOOL_ROUTING_PROMPT_PATH.read_text(encoding="utf-8").strip()
    replacements = 0
    result: list[dict[str, Any]] = []
    for message in projected:
        copied = dict(message)
        content = copied.get("content")
        if copied.get("role") == "system" and isinstance(content, str):
            if old_system not in content:
                raise DeepSeekClientError(
                    "tool_routing_prompt_projection: frozen system Prompt marker missing"
                )
            copied["content"] = content.replace(old_system, new_system, 1)
            replacements += 1
        result.append(copied)
    if replacements != 1:
        raise DeepSeekClientError(
            "tool_routing_prompt_projection: exactly one system Prompt is required"
        )
    return result


@dataclass
class NativeToolOnlineCandidateToolRoutingV1(
    NativeToolOnlineCandidateV2_3_4_2
):
    runtime_message_projector: Callable[
        [list[dict[str, Any]]], list[dict[str, Any]]
    ] = field(
        init=False,
        default_factory=lambda: project_runtime_messages_tool_routing_v1,
        repr=False,
    )


__all__ = [
    "NativeToolOnlineCandidateToolRoutingV1",
    "TOOL_ROUTING_PROMPT_PATH",
    "TOOL_ROUTING_PROMPT_VERSION",
    "project_runtime_messages_tool_routing_v1",
]
