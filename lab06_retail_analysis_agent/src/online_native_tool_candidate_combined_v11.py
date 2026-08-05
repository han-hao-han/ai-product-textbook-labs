"""Combined v10 with explicit required-atom selection guidance."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from src.atom_selection_required_guard_v11 import (
    build_atom_selection_instruction_v11,
)
from src.online_native_tool_candidate_combined_v10 import (
    NativeToolOnlineCandidateCombinedV10,
)


COMBINED_PROMPT_VERSION = (
    "1.5.6-h3-native-tool-routing-v3-report-v5-claim-groups-v10-"
    "atom-required-v11"
)


@dataclass
class NativeToolOnlineCandidateCombinedV11(
    NativeToolOnlineCandidateCombinedV10
):
    selection_instruction_builder: Callable[[Any], str] = field(
        init=False,
        default_factory=lambda: build_atom_selection_instruction_v11,
        repr=False,
    )


__all__ = [
    "COMBINED_PROMPT_VERSION",
    "NativeToolOnlineCandidateCombinedV11",
]
