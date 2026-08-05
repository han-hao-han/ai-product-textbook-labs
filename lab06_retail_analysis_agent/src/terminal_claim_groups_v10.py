"""Build deterministic claim-local FACT groups for the terminal report."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable

from src.report_terminal_protocol_guard_v2_3_4_2 import (
    IsolatedTerminalContextV2_3_4_2,
)
from src.terminal_structural_guard_v9 import required_summary_fact_ids_v9


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TERMINAL_CLAIM_GROUPS_PROMPT_PATH = (
    PROJECT_ROOT / "prompts" / "native_tool_terminal_claim_groups_v10.md"
)
TERMINAL_CLAIM_GROUPS_VERSION = "1.5.6-h3-terminal-claim-groups-v10"
CLAIM_GROUPS_MARKER = "{{CLAIM_FACT_GROUPS}}"
MAX_SLOT_CLAIMS = 12


def _dimension_key(reference: Any) -> tuple[tuple[str, str], ...]:
    return tuple((item.name, item.value) for item in reference.dimensions)


def required_claim_fact_groups_v10(references: Iterable[Any]) -> list[list[str]]:
    facts = [item for item in references if item.evidence_type == "FACT"]
    required_ids = required_summary_fact_ids_v9(facts)
    by_id = {item.fact_id: item for item in facts}
    grouped: dict[tuple[Any, ...], list[str]] = {}
    order: list[tuple[Any, ...]] = []
    for fact_id in required_ids:
        fact = by_id[fact_id]
        key = (
            _dimension_key(fact),
            fact.period,
            fact.start_date,
            fact.end_date,
        )
        if key not in grouped:
            order.append(key)
            grouped[key] = []
        grouped[key].append(fact_id)
    groups = [grouped[key] for key in order]
    if not groups or len(groups) > MAX_SLOT_CLAIMS:
        raise ValueError("terminal_claim_group_capacity")
    return groups


def project_terminal_context_v10(
    context: IsolatedTerminalContextV2_3_4_2,
) -> IsolatedTerminalContextV2_3_4_2:
    slots = list(context.model_visible.slots)
    result_slot = slots[1]
    groups = required_claim_fact_groups_v10(result_slot.allowed_evidence)
    required_ids = {fact_id for group in groups for fact_id in group}
    selected_evidence = [
        item
        for item in result_slot.allowed_evidence
        if item.evidence_type == "FACT" and item.fact_id in required_ids
    ]
    slots[1] = result_slot.model_copy(
        update={
            "selected_atom_ids": [],
            "support_atoms": [],
            "allowed_evidence": selected_evidence,
            "allowed_selection_limit_values": [],
            "allowed_superlative_metrics": list(dict.fromkeys(
                item.metric
                for item in selected_evidence
                if item.rank == 1 and item.metric is not None
            )),
        }
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
    group_text = "|".join("+".join(group) for group in groups)
    template = TERMINAL_CLAIM_GROUPS_PROMPT_PATH.read_text(
        encoding="utf-8"
    ).strip()
    instruction = template.replace(CLAIM_GROUPS_MARKER, group_text)
    visible = context.model_visible.model_copy(
        update={"slots": slots, "instruction": instruction}
    )
    return replace(context, model_visible=visible)


__all__ = [
    "CLAIM_GROUPS_MARKER",
    "TERMINAL_CLAIM_GROUPS_PROMPT_PATH",
    "TERMINAL_CLAIM_GROUPS_VERSION",
    "project_terminal_context_v10",
    "required_claim_fact_groups_v10",
]
