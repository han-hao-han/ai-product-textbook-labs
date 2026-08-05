"""Combined v7 with isolated incomplete-period terminal guidance v8."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from src.online_native_tool_candidate_combined_v7 import (
    NativeToolOnlineCandidateCombinedV7,
)
from src.terminal_summary_coverage_v8 import project_terminal_context_v8


COMBINED_PROMPT_VERSION = (
    "1.5.6-h3-native-tool-routing-v3-report-v5-summary-coverage-v8"
)


@dataclass
class NativeToolOnlineCandidateCombinedV8(
    NativeToolOnlineCandidateCombinedV7
):
    terminal_context_projector: Callable[[Any], Any] = field(
        init=False,
        default_factory=lambda: project_terminal_context_v8,
        repr=False,
    )


__all__ = [
    "COMBINED_PROMPT_VERSION",
    "NativeToolOnlineCandidateCombinedV8",
]
