"""Combined v19 with a local incomplete-period FACT exception."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from src.online_native_tool_candidate_combined_v19 import NativeToolOnlineCandidateCombinedV19
from src.terminal_narrative_evidence_expression_v18 import terminal_narrative_evidence_issues_v18


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROMPT_PATH = PROJECT_ROOT / "prompts" / "native_tool_incomplete_period_exception_v20.md"
COMBINED_PROMPT_VERSION = (
    "1.5.6-h3-native-tool-routing-v3-report-v5-claim-groups-v10-"
    "atom-required-v11-slot2-literal-v12-feedback-v13-protocol-v14-"
    "evidence-completeness-v15-fact-expression-v16-chart-aware-v17-"
    "narrative-evidence-v18-protocol-disambiguation-v19-"
    "incomplete-period-exception-v20"
)


@dataclass
class NativeToolOnlineCandidateCombinedV20(NativeToolOnlineCandidateCombinedV19):
    terminal_draft_validator: Callable[[Any], list[dict[str, Any]]] = field(
        init=False, default_factory=lambda: terminal_narrative_evidence_issues_v18,
        repr=False,
    )
    terminal_repair_instruction: str = field(
        init=False, default_factory=lambda: PROMPT_PATH.read_text(encoding="utf-8").strip(),
        repr=False,
    )


__all__ = ["COMBINED_PROMPT_VERSION", "NativeToolOnlineCandidateCombinedV20"]
