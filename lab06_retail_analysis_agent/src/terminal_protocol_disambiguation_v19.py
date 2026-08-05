"""Resolve incomplete-period placement and safe slot-binding feedback."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from src.report_evidence_semantic_boundary_v2_2_2 import canonical_numeric_tokens
from src.terminal_report_feedback_v13 import terminal_report_issues_v13
from src.terminal_protocol_feedback_v14 import terminal_protocol_issues_v14


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_DISAMBIGUATION_PROMPT_PATH = (
    PROJECT_ROOT / "prompts" / "native_tool_protocol_disambiguation_v19.md"
)
PROTOCOL_DISAMBIGUATION_VERSION = "1.5.6-h3-terminal-protocol-disambiguation-v19"
CHART_EVIDENCE_SECTION_INDEX = 2


def terminal_draft_issues_v19(response: Any) -> list[dict[str, Any]]:
    issues = terminal_report_issues_v13(response)
    for section_index, section in enumerate(response.report.sections):
        if section_index == CHART_EVIDENCE_SECTION_INDEX:
            continue
        for claim_index, claim in enumerate(section.claims):
            statement_tokens = canonical_numeric_tokens(claim.statement)
            for reference in claim.evidence:
                if reference.evidence_type == "REQUEST":
                    for token in sorted(canonical_numeric_tokens(reference.value) - statement_tokens):
                        issues.append({
                            "code": "request_value_not_expressed",
                            "location": f"sections[{section_index}].claims[{claim_index}]",
                            "request_id": reference.request_id,
                            "required_literal": token,
                        })
                elif reference.evidence_type == "FACT":
                    if reference.metric == "incomplete_period":
                        continue
                    accepted = (
                        canonical_numeric_tokens(reference.value)
                        | canonical_numeric_tokens(reference.display_value)
                    )
                    if accepted and not accepted & statement_tokens:
                        issues.append({
                            "code": "fact_value_not_expressed",
                            "location": f"sections[{section_index}].claims[{claim_index}]",
                            "fact_id": reference.fact_id,
                            "required_value": reference.value,
                            "accepted_display_value": reference.display_value,
                        })
    return issues


def terminal_protocol_issues_v19(code: str, message: str, content: str) -> list[dict[str, Any]]:
    inherited = terminal_protocol_issues_v14(code, message, content)
    if inherited:
        return inherited
    if code != "slot_report_binding_validation":
        return []
    match = re.search(r"(SLOT-\d{3}) report section borrowed evidence", message)
    return [{
        "code": code,
        "location": match.group(1) if match else "report.sections",
        "message": message,
        "instruction": "remove borrowed evidence and use only this slot's local evidence",
    }]


def load_protocol_disambiguation_prompt_v19() -> str:
    return PROTOCOL_DISAMBIGUATION_PROMPT_PATH.read_text(encoding="utf-8").strip()


__all__ = [
    "PROTOCOL_DISAMBIGUATION_PROMPT_PATH", "PROTOCOL_DISAMBIGUATION_VERSION",
    "load_protocol_disambiguation_prompt_v19", "terminal_draft_issues_v19",
    "terminal_protocol_issues_v19",
]
