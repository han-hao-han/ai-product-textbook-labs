"""Combined v5 Prompt with final-envelope coverage guidance v6."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from src.online_native_tool_candidate_combined_v5 import (
    NativeToolOnlineCandidateCombinedV5,
)
from src.terminal_coverage_guidance_v6 import (
    TERMINAL_COVERAGE_VERSION,
    project_terminal_context_v6,
)


COMBINED_PROMPT_VERSION = (
    "1.5.6-h3-native-tool-routing-v3-report-v5-terminal-coverage-v6"
)


@dataclass
class NativeToolOnlineCandidateCombinedV6(
    NativeToolOnlineCandidateCombinedV5
):
    terminal_context_projector: Callable[[Any], Any] = field(
        init=False,
        default_factory=lambda: project_terminal_context_v6,
        repr=False,
    )


__all__ = [
    "COMBINED_PROMPT_VERSION",
    "NativeToolOnlineCandidateCombinedV6",
    "TERMINAL_COVERAGE_VERSION",
]
