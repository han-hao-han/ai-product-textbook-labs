"""Combined v9 with deterministic terminal claim-local FACT groups."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from src.online_native_tool_candidate_combined_v9 import (
    NativeToolOnlineCandidateCombinedV9,
)
from src.terminal_claim_groups_v10 import project_terminal_context_v10


COMBINED_PROMPT_VERSION = (
    "1.5.6-h3-native-tool-routing-v3-report-v5-claim-groups-v10"
)


@dataclass
class NativeToolOnlineCandidateCombinedV10(
    NativeToolOnlineCandidateCombinedV9
):
    terminal_context_projector: Callable[[Any], Any] = field(
        init=False,
        default_factory=lambda: project_terminal_context_v10,
        repr=False,
    )


__all__ = [
    "COMBINED_PROMPT_VERSION",
    "NativeToolOnlineCandidateCombinedV10",
]
