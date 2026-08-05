"""Combined v17 with chart-aware REQUEST and FACT expression."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from src.online_native_tool_candidate_combined_v17 import NativeToolOnlineCandidateCombinedV17
from src.terminal_narrative_evidence_expression_v18 import (
    load_narrative_evidence_prompt_v18,
    terminal_narrative_evidence_issues_v18,
)


COMBINED_PROMPT_VERSION = (
    "1.5.6-h3-native-tool-routing-v3-report-v5-claim-groups-v10-"
    "atom-required-v11-slot2-literal-v12-feedback-v13-protocol-v14-"
    "evidence-completeness-v15-fact-expression-v16-chart-aware-v17-"
    "narrative-evidence-v18"
)


@dataclass
class NativeToolOnlineCandidateCombinedV18(NativeToolOnlineCandidateCombinedV17):
    terminal_draft_validator: Callable[[Any], list[dict[str, Any]]] = field(
        init=False, default_factory=lambda: terminal_narrative_evidence_issues_v18,
        repr=False,
    )
    terminal_repair_instruction: str = field(
        init=False, default_factory=load_narrative_evidence_prompt_v18, repr=False,
    )


__all__ = ["COMBINED_PROMPT_VERSION", "NativeToolOnlineCandidateCombinedV18"]
