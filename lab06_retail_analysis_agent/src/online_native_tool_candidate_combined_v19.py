"""Combined v18 with protocol conflict disambiguation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from src.online_native_tool_candidate_combined_v18 import NativeToolOnlineCandidateCombinedV18
from src.terminal_protocol_disambiguation_v19 import (
    load_protocol_disambiguation_prompt_v19,
    terminal_draft_issues_v19,
    terminal_protocol_issues_v19,
)


COMBINED_PROMPT_VERSION = (
    "1.5.6-h3-native-tool-routing-v3-report-v5-claim-groups-v10-"
    "atom-required-v11-slot2-literal-v12-feedback-v13-protocol-v14-"
    "evidence-completeness-v15-fact-expression-v16-chart-aware-v17-"
    "narrative-evidence-v18-protocol-disambiguation-v19"
)


@dataclass
class NativeToolOnlineCandidateCombinedV19(NativeToolOnlineCandidateCombinedV18):
    terminal_draft_validator: Callable[[Any], list[dict[str, Any]]] = field(
        init=False, default_factory=lambda: terminal_draft_issues_v19, repr=False,
    )
    terminal_protocol_error_feedback_builder: Callable[
        [str, str, str], list[dict[str, Any]]
    ] = field(
        init=False, default_factory=lambda: terminal_protocol_issues_v19, repr=False,
    )
    terminal_repair_instruction: str = field(
        init=False, default_factory=load_protocol_disambiguation_prompt_v19, repr=False,
    )


__all__ = ["COMBINED_PROMPT_VERSION", "NativeToolOnlineCandidateCombinedV19"]
