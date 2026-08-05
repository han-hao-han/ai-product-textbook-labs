"""Combined v11 with explicit SLOT-002 non-local literal isolation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from src.online_native_tool_candidate_combined_v11 import (
    NativeToolOnlineCandidateCombinedV11,
)
from src.terminal_slot2_forbidden_v12 import project_terminal_context_v12


COMBINED_PROMPT_VERSION = (
    "1.5.6-h3-native-tool-routing-v3-report-v5-claim-groups-v10-"
    "atom-required-v11-slot2-literal-v12"
)


@dataclass
class NativeToolOnlineCandidateCombinedV12(
    NativeToolOnlineCandidateCombinedV11
):
    terminal_context_projector: Callable[[Any], Any] = field(
        init=False,
        default_factory=lambda: project_terminal_context_v12,
        repr=False,
    )


__all__ = [
    "COMBINED_PROMPT_VERSION",
    "NativeToolOnlineCandidateCombinedV12",
]
