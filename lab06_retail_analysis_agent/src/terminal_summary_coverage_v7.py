"""Select deterministic summary FACT coverage for the final model envelope."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable

from src.report_terminal_protocol_guard_v2_3_4_2 import (
    IsolatedTerminalContextV2_3_4_2,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TERMINAL_SUMMARY_PROMPT_PATH = (
    PROJECT_ROOT / "prompts" / "native_tool_terminal_summary_coverage_v7.md"
)
TERMINAL_SUMMARY_VERSION = "1.5.6-h3-terminal-summary-coverage-v7"
REQUIRED_IDS_MARKER = "{{REQUIRED_FACT_IDS}}"


def _dimensions(reference: Any) -> dict[str, str]:
    return {item.name: item.value for item in reference.dimensions}


def required_summary_fact_ids(references: Iterable[Any]) -> list[str]:
    facts = [item for item in references if item.evidence_type == "FACT"]
    peak_months = {
        item.value for item in facts if item.metric == "peak_period"
    }
    eligible = []
    for fact in facts:
        month = _dimensions(fact).get("month")
        if month is not None and month not in peak_months:
            continue
        eligible.append(fact)

    by_value: dict[tuple[str, str, str, str], Any] = {}
    order: list[tuple[str, str, str, str]] = []
    for fact in eligible:
        key = (fact.metric, fact.value, fact.display_value, fact.unit)
        previous = by_value.get(key)
        if previous is None:
            order.append(key)
            by_value[key] = fact
        elif previous.rank is None and fact.rank is not None:
            by_value[key] = fact
    return [by_value[key].fact_id for key in order]


def project_terminal_context_v7(
    context: IsolatedTerminalContextV2_3_4_2,
) -> IsolatedTerminalContextV2_3_4_2:
    result_slot = context.model_visible.slots[1]
    required_ids = required_summary_fact_ids(result_slot.allowed_evidence)
    template = TERMINAL_SUMMARY_PROMPT_PATH.read_text(
        encoding="utf-8"
    ).strip()
    instruction = template.replace(
        REQUIRED_IDS_MARKER, ",".join(required_ids)
    )
    visible = context.model_visible.model_copy(
        update={"instruction": instruction}
    )
    return replace(context, model_visible=visible)


__all__ = [
    "REQUIRED_IDS_MARKER",
    "TERMINAL_SUMMARY_PROMPT_PATH",
    "TERMINAL_SUMMARY_VERSION",
    "project_terminal_context_v7",
    "required_summary_fact_ids",
]
