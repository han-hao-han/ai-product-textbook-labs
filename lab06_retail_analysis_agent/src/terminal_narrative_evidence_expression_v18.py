"""Require evidence-value expression only in narrative report sections."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.report_evidence_semantic_boundary_v2_2_2 import canonical_numeric_tokens
from src.terminal_report_feedback_v13 import terminal_report_issues_v13


PROJECT_ROOT = Path(__file__).resolve().parents[1]
NARRATIVE_EVIDENCE_PROMPT_PATH = (
    PROJECT_ROOT / "prompts" / "native_tool_narrative_evidence_feedback_v18.md"
)
NARRATIVE_EVIDENCE_VERSION = "1.5.6-h3-terminal-narrative-evidence-v18"
CHART_EVIDENCE_SECTION_INDEX = 2


def terminal_narrative_evidence_issues_v18(response: Any) -> list[dict[str, Any]]:
    issues = terminal_report_issues_v13(response)
    for section_index, section in enumerate(response.report.sections):
        if section_index == CHART_EVIDENCE_SECTION_INDEX:
            continue
        for claim_index, claim in enumerate(section.claims):
            statement_tokens = canonical_numeric_tokens(claim.statement)
            for reference in claim.evidence:
                if reference.evidence_type == "REQUEST":
                    required = canonical_numeric_tokens(reference.value)
                    for token in sorted(required - statement_tokens):
                        issues.append({
                            "code": "request_value_not_expressed",
                            "location": f"sections[{section_index}].claims[{claim_index}]",
                            "request_id": reference.request_id,
                            "parameter_name": reference.parameter_name,
                            "required_literal": token,
                        })
                elif reference.evidence_type == "FACT":
                    accepted = (
                        canonical_numeric_tokens(reference.value)
                        | canonical_numeric_tokens(reference.display_value)
                    )
                    if accepted and not accepted & statement_tokens:
                        issues.append({
                            "code": "fact_value_not_expressed",
                            "location": f"sections[{section_index}].claims[{claim_index}]",
                            "fact_id": reference.fact_id,
                            "metric": reference.metric,
                            "required_value": reference.value,
                            "accepted_display_value": reference.display_value,
                        })
    return issues


def load_narrative_evidence_prompt_v18() -> str:
    return NARRATIVE_EVIDENCE_PROMPT_PATH.read_text(encoding="utf-8").strip()


__all__ = [
    "CHART_EVIDENCE_SECTION_INDEX", "NARRATIVE_EVIDENCE_PROMPT_PATH",
    "NARRATIVE_EVIDENCE_VERSION", "load_narrative_evidence_prompt_v18",
    "terminal_narrative_evidence_issues_v18",
]
