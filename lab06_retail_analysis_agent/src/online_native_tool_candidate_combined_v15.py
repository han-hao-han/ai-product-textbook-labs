"""Combined v14 with REQUEST-value completeness feedback."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from src.online_native_tool_candidate_combined_v14 import (
    NativeToolOnlineCandidateCombinedV14,
)
from src.terminal_evidence_completeness_v15 import (
    load_evidence_completeness_prompt_v15,
    terminal_evidence_issues_v15,
)


COMBINED_PROMPT_VERSION = (
    "1.5.6-h3-native-tool-routing-v3-report-v5-claim-groups-v10-"
    "atom-required-v11-slot2-literal-v12-feedback-v13-protocol-v14-"
    "evidence-completeness-v15"
)


@dataclass
class NativeToolOnlineCandidateCombinedV15(
    NativeToolOnlineCandidateCombinedV14
):
    terminal_draft_validator: Callable[[Any], list[dict[str, Any]]] = field(
        init=False,
        default_factory=lambda: terminal_evidence_issues_v15,
        repr=False,
    )
    terminal_repair_instruction: str = field(
        init=False,
        default_factory=load_evidence_completeness_prompt_v15,
        repr=False,
    )


__all__ = [
    "COMBINED_PROMPT_VERSION",
    "NativeToolOnlineCandidateCombinedV15",
]
