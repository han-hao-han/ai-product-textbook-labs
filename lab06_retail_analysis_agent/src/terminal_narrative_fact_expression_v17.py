"""Require FACT expression in narrative claims, not chart data claims."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.report_evidence_semantic_boundary_v2_2_2 import canonical_numeric_tokens
from src.terminal_evidence_completeness_v15 import terminal_evidence_issues_v15


PROJECT_ROOT = Path(__file__).resolve().parents[1]
NARRATIVE_FACT_PROMPT_PATH = (
    PROJECT_ROOT / "prompts" / "native_tool_narrative_fact_feedback_v17.md"
)
NARRATIVE_FACT_VERSION = "1.5.6-h3-terminal-narrative-fact-v17"
CHART_EVIDENCE_SECTION_INDEX = 2


def terminal_narrative_fact_issues_v17(response: Any) -> list[dict[str, Any]]:
    issues = terminal_evidence_issues_v15(response)
    for section_index, section in enumerate(response.report.sections):
        if section_index == CHART_EVIDENCE_SECTION_INDEX:
            continue
        for claim_index, claim in enumerate(section.claims):
            statement_tokens = canonical_numeric_tokens(claim.statement)
            for reference in claim.evidence:
                if reference.evidence_type != "FACT":
                    continue
                accepted_tokens = (
                    canonical_numeric_tokens(reference.value)
                    | canonical_numeric_tokens(reference.display_value)
                )
                if not accepted_tokens or accepted_tokens & statement_tokens:
                    continue
                issues.append(
                    {
                        "code": "fact_value_not_expressed",
                        "location": f"sections[{section_index}].claims[{claim_index}]",
                        "fact_id": reference.fact_id,
                        "metric": reference.metric,
                        "required_value": reference.value,
                        "accepted_display_value": reference.display_value,
                        "instruction": (
                            "state this FACT value or its display value in the "
                            "same narrative claim; preserve the local FACT evidence"
                        ),
                    }
                )
    return issues


def load_narrative_fact_prompt_v17() -> str:
    return NARRATIVE_FACT_PROMPT_PATH.read_text(encoding="utf-8").strip()


__all__ = [
    "CHART_EVIDENCE_SECTION_INDEX", "NARRATIVE_FACT_PROMPT_PATH",
    "NARRATIVE_FACT_VERSION", "load_narrative_fact_prompt_v17",
    "terminal_narrative_fact_issues_v17",
]
