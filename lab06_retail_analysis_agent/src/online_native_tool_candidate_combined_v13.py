"""Combined v12 with one bounded deterministic report correction response."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from src.online_native_tool_candidate_combined_v12 import (
    NativeToolOnlineCandidateCombinedV12,
)
from src.terminal_report_feedback_v13 import (
    load_report_validation_feedback_prompt_v13,
    terminal_report_issues_v13,
)


COMBINED_PROMPT_VERSION = (
    "1.5.6-h3-native-tool-routing-v3-report-v5-claim-groups-v10-"
    "atom-required-v11-slot2-literal-v12-feedback-v13"
)


@dataclass
class NativeToolOnlineCandidateCombinedV13(
    NativeToolOnlineCandidateCombinedV12
):
    terminal_draft_validator: Callable[[Any], list[dict[str, Any]]] = field(
        init=False,
        default_factory=lambda: terminal_report_issues_v13,
        repr=False,
    )
    terminal_repair_limit: int = field(init=False, default=1, repr=False)
    terminal_repair_instruction: str = field(
        init=False,
        default_factory=load_report_validation_feedback_prompt_v13,
        repr=False,
    )


__all__ = [
    "COMBINED_PROMPT_VERSION",
    "NativeToolOnlineCandidateCombinedV13",
]
