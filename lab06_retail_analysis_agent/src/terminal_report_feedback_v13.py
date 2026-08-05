"""Preflight deterministic numeric traceability before publishing a report."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.report_evidence_semantic_boundary_v2_2_2 import (
    canonical_numeric_tokens,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_VALIDATION_FEEDBACK_PROMPT_PATH = (
    PROJECT_ROOT / "prompts" / "native_tool_report_validation_feedback_v13.md"
)
REPORT_VALIDATION_FEEDBACK_VERSION = (
    "1.5.6-h3-report-validation-feedback-v13"
)


def _allowed_tokens(reference: Any) -> set[str]:
    if reference.evidence_type == "FACT":
        candidates = [
            reference.value,
            reference.display_value,
            str(reference.rank) if reference.rank is not None else "",
            reference.start_date or "",
            reference.end_date or "",
            *(item.value for item in reference.dimensions),
        ]
        if (
            reference.start_date is not None
            and reference.end_date is not None
            and reference.start_date[:7] == reference.end_date[:7]
        ):
            candidates.append(reference.start_date[:7])
    elif reference.evidence_type == "REQUEST":
        candidates = [reference.value]
    else:
        candidates = [reference.message]
    allowed: set[str] = set()
    for candidate in candidates:
        allowed.update(canonical_numeric_tokens(candidate))
    return allowed


def terminal_report_issues_v13(response: Any) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for section_index, section in enumerate(response.report.sections):
        for claim_index, claim in enumerate(section.claims):
            allowed: set[str] = set()
            for reference in claim.evidence:
                allowed.update(_allowed_tokens(reference))
            unsupported = canonical_numeric_tokens(claim.statement) - allowed
            for token in sorted(unsupported):
                issues.append(
                    {
                        "code": "untraceable_numeric_token",
                        "location": (
                            f"sections[{section_index}].claims[{claim_index}]"
                        ),
                        "unsupported_literal": token,
                        "instruction": (
                            "remove this literal from this claim; do not add "
                            "cross-slot evidence"
                        ),
                    }
                )
    return issues


def load_report_validation_feedback_prompt_v13() -> str:
    return REPORT_VALIDATION_FEEDBACK_PROMPT_PATH.read_text(
        encoding="utf-8"
    ).strip()


__all__ = [
    "REPORT_VALIDATION_FEEDBACK_PROMPT_PATH",
    "REPORT_VALIDATION_FEEDBACK_VERSION",
    "load_report_validation_feedback_prompt_v13",
    "terminal_report_issues_v13",
]
