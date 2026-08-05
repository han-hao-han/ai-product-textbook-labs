"""Combined v15 with local FACT-expression feedback."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from src.online_native_tool_candidate_combined_v15 import (
    NativeToolOnlineCandidateCombinedV15,
)
from src.terminal_fact_expression_v16 import (
    load_fact_expression_prompt_v16,
    terminal_fact_expression_issues_v16,
)


COMBINED_PROMPT_VERSION = (
    "1.5.6-h3-native-tool-routing-v3-report-v5-claim-groups-v10-"
    "atom-required-v11-slot2-literal-v12-feedback-v13-protocol-v14-"
    "evidence-completeness-v15-fact-expression-v16"
)


@dataclass
class NativeToolOnlineCandidateCombinedV16(
    NativeToolOnlineCandidateCombinedV15
):
    terminal_draft_validator: Callable[[Any], list[dict[str, Any]]] = field(
        init=False,
        default_factory=lambda: terminal_fact_expression_issues_v16,
        repr=False,
    )
    terminal_repair_instruction: str = field(
        init=False,
        default_factory=load_fact_expression_prompt_v16,
        repr=False,
    )


__all__ = ["COMBINED_PROMPT_VERSION", "NativeToolOnlineCandidateCombinedV16"]
