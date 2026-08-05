"""Preflight that numeric FACT evidence is expressed in its local claim."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.report_evidence_semantic_boundary_v2_2_2 import (
    canonical_numeric_tokens,
)
from src.terminal_evidence_completeness_v15 import terminal_evidence_issues_v15


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FACT_EXPRESSION_PROMPT_PATH = (
    PROJECT_ROOT / "prompts" / "native_tool_fact_expression_feedback_v16.md"
)
FACT_EXPRESSION_VERSION = "1.5.6-h3-terminal-fact-expression-v16"


def terminal_fact_expression_issues_v16(response: Any) -> list[dict[str, Any]]:
    """Add the missing half of local FACT traceability: evidence -> prose."""

    issues = terminal_evidence_issues_v15(response)
    for section_index, section in enumerate(response.report.sections):
        for claim_index, claim in enumerate(section.claims):
            statement_tokens = canonical_numeric_tokens(claim.statement)
            for reference in claim.evidence:
                if reference.evidence_type != "FACT":
                    continue
                raw_tokens = canonical_numeric_tokens(reference.value)
                display_tokens = canonical_numeric_tokens(reference.display_value)
                accepted_tokens = raw_tokens | display_tokens
                if not accepted_tokens or accepted_tokens & statement_tokens:
                    continue
                issues.append(
                    {
                        "code": "fact_value_not_expressed",
                        "location": (
                            f"sections[{section_index}].claims[{claim_index}]"
                        ),
                        "fact_id": reference.fact_id,
                        "metric": reference.metric,
                        "required_value": reference.value,
                        "accepted_display_value": reference.display_value,
                        "instruction": (
                            "state this FACT value or its display value in the "
                            "same claim; preserve the local FACT evidence"
                        ),
                    }
                )
    return issues


def load_fact_expression_prompt_v16() -> str:
    return FACT_EXPRESSION_PROMPT_PATH.read_text(encoding="utf-8").strip()


__all__ = [
    "FACT_EXPRESSION_PROMPT_PATH",
    "FACT_EXPRESSION_VERSION",
    "load_fact_expression_prompt_v16",
    "terminal_fact_expression_issues_v16",
]
