"""Add explicit non-local incomplete-period literals to the SLOT-002 guard."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable

from src.report_terminal_protocol_guard_v2_3_4_2 import (
    IsolatedTerminalContextV2_3_4_2,
)
from src.terminal_claim_groups_v10 import project_terminal_context_v10


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SLOT2_FORBIDDEN_PROMPT_PATH = (
    PROJECT_ROOT / "prompts" / "native_tool_terminal_slot2_forbidden_v12.md"
)
SLOT2_FORBIDDEN_VERSION = "1.5.6-h3-terminal-slot2-forbidden-v12"
FORBIDDEN_LITERAL_MARKER = "{{FORBIDDEN_LITERAL_VALUES}}"
V10_GENERIC_GUARD = (
    "If peak_period exists, SLOT-002 must not mention excluded/incomplete "
    "periods; use only SLOT-001 and SLOT-006."
)


def slot2_forbidden_literals_v12(references: Iterable[Any]) -> list[str]:
    values: list[str] = []
    for item in references:
        if (
            item.evidence_type == "FACT"
            and item.metric == "incomplete_period"
        ):
            values.append(item.value)
        elif (
            item.evidence_type == "REQUEST"
            and item.parameter_name == "excluded_period"
        ):
            values.append(item.value)
    return list(dict.fromkeys(values))


def project_terminal_context_v12(
    context: IsolatedTerminalContextV2_3_4_2,
) -> IsolatedTerminalContextV2_3_4_2:
    projected = project_terminal_context_v10(context)
    source_references = [
        item
        for slot in context.model_visible.slots
        for item in slot.allowed_evidence
    ]
    forbidden = slot2_forbidden_literals_v12(source_references)
    if not forbidden:
        return projected
    suffix = SLOT2_FORBIDDEN_PROMPT_PATH.read_text(
        encoding="utf-8"
    ).strip().replace(FORBIDDEN_LITERAL_MARKER, ",".join(forbidden))
    if V10_GENERIC_GUARD not in projected.model_visible.instruction:
        raise ValueError("terminal_slot2_generic_guard_missing")
    instruction = projected.model_visible.instruction.replace(
        V10_GENERIC_GUARD, suffix
    )
    if len(instruction) > 1200:
        raise ValueError("terminal_slot2_forbidden_instruction_capacity")
    visible = projected.model_visible.model_copy(
        update={"instruction": instruction}
    )
    return replace(projected, model_visible=visible)


__all__ = [
    "SLOT2_FORBIDDEN_PROMPT_PATH",
    "SLOT2_FORBIDDEN_VERSION",
    "project_terminal_context_v12",
    "slot2_forbidden_literals_v12",
]
