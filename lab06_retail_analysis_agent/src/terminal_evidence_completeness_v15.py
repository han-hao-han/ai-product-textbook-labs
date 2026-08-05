"""Preflight local REQUEST-value expression before formal report acceptance."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.report_evidence_semantic_boundary_v2_2_2 import (
    canonical_numeric_tokens,
)
from src.terminal_report_feedback_v13 import terminal_report_issues_v13


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_COMPLETENESS_PROMPT_PATH = (
    PROJECT_ROOT / "prompts" / "native_tool_evidence_completeness_feedback_v15.md"
)
EVIDENCE_COMPLETENESS_VERSION = (
    "1.5.6-h3-terminal-evidence-completeness-v15"
)


def terminal_evidence_issues_v15(response: Any) -> list[dict[str, Any]]:
    """Combine numeric traceability with local REQUEST-value completeness."""

    issues = terminal_report_issues_v13(response)
    for section_index, section in enumerate(response.report.sections):
        for claim_index, claim in enumerate(section.claims):
            statement_tokens = canonical_numeric_tokens(claim.statement)
            for reference in claim.evidence:
                if reference.evidence_type != "REQUEST":
                    continue
                required_tokens = canonical_numeric_tokens(reference.value)
                for token in sorted(required_tokens - statement_tokens):
                    issues.append(
                        {
                            "code": "request_value_not_expressed",
                            "location": (
                                f"sections[{section_index}].claims[{claim_index}]"
                            ),
                            "request_id": reference.request_id,
                            "parameter_name": reference.parameter_name,
                            "required_literal": token,
                            "instruction": (
                                "state this literal in the same claim that cites "
                                "this REQUEST; preserve the local REQUEST evidence"
                            ),
                        }
                    )
    return issues


def load_evidence_completeness_prompt_v15() -> str:
    return EVIDENCE_COMPLETENESS_PROMPT_PATH.read_text(
        encoding="utf-8"
    ).strip()


__all__ = [
    "EVIDENCE_COMPLETENESS_PROMPT_PATH",
    "EVIDENCE_COMPLETENESS_VERSION",
    "load_evidence_completeness_prompt_v15",
    "terminal_evidence_issues_v15",
]
