"""V9 structurally narrows final-report evidence without authoring claims."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from src.report_terminal_protocol_guard_v2_3_4_2 import (
    IsolatedTerminalContextV2_3_4_2,
)
from src.terminal_summary_coverage_v7 import required_summary_fact_ids


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TERMINAL_STRUCTURAL_PROMPT_PATH = (
    PROJECT_ROOT / "prompts" / "native_tool_terminal_structural_guard_v9.md"
)
TERMINAL_STRUCTURAL_VERSION = "1.5.6-h3-terminal-structural-guard-v9"
REQUIRED_IDS_MARKER = "{{REQUIRED_FACT_IDS}}"


def required_summary_fact_ids_v9(references) -> list[str]:
    selected = required_summary_fact_ids(references)
    by_id = {
        item.fact_id: item
        for item in references
        if item.evidence_type == "FACT"
    }
    has_peak = any(item.metric == "peak_period" for item in by_id.values())
    if not has_peak:
        return selected
    return [
        fact_id
        for fact_id in selected
        if by_id[fact_id].metric != "incomplete_period"
    ]


def project_terminal_context_v9(
    context: IsolatedTerminalContextV2_3_4_2,
) -> IsolatedTerminalContextV2_3_4_2:
    slots = list(context.model_visible.slots)
    required_ids = required_summary_fact_ids_v9(
        slots[1].allowed_evidence
    )
    for index in (3, 4):
        slots[index] = slots[index].model_copy(
            update={
                "selected_atom_ids": [],
                "support_atoms": [],
                "allowed_evidence": [],
                "allowed_selection_limit_values": [],
                "allowed_superlative_metrics": [],
            }
        )
    template = TERMINAL_STRUCTURAL_PROMPT_PATH.read_text(
        encoding="utf-8"
    ).strip()
    instruction = template.replace(
        REQUIRED_IDS_MARKER, ",".join(required_ids)
    )
    visible = context.model_visible.model_copy(
        update={"slots": slots, "instruction": instruction}
    )
    return replace(context, model_visible=visible)


__all__ = [
    "TERMINAL_STRUCTURAL_PROMPT_PATH",
    "TERMINAL_STRUCTURAL_VERSION",
    "project_terminal_context_v9",
    "required_summary_fact_ids_v9",
]
