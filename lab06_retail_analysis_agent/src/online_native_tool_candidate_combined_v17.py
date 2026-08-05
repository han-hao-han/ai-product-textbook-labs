"""Combined v16 with chart-aware narrative FACT expression."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from src.online_native_tool_candidate_combined_v16 import (
    NativeToolOnlineCandidateCombinedV16,
)
from src.terminal_narrative_fact_expression_v17 import (
    load_narrative_fact_prompt_v17,
    terminal_narrative_fact_issues_v17,
)


COMBINED_PROMPT_VERSION = (
    "1.5.6-h3-native-tool-routing-v3-report-v5-claim-groups-v10-"
    "atom-required-v11-slot2-literal-v12-feedback-v13-protocol-v14-"
    "evidence-completeness-v15-fact-expression-v16-chart-aware-v17"
)


@dataclass
class NativeToolOnlineCandidateCombinedV17(
    NativeToolOnlineCandidateCombinedV16
):
    terminal_draft_validator: Callable[[Any], list[dict[str, Any]]] = field(
        init=False,
        default_factory=lambda: terminal_narrative_fact_issues_v17,
        repr=False,
    )
    terminal_repair_instruction: str = field(
        init=False,
        default_factory=load_narrative_fact_prompt_v17,
        repr=False,
    )


__all__ = ["COMBINED_PROMPT_VERSION", "NativeToolOnlineCandidateCombinedV17"]
