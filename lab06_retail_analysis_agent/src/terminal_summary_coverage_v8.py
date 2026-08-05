"""V8 final-envelope guidance isolates incomplete-period evidence claims."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from src.report_terminal_protocol_guard_v2_3_4_2 import (
    IsolatedTerminalContextV2_3_4_2,
)
from src.terminal_summary_coverage_v7 import required_summary_fact_ids


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TERMINAL_SUMMARY_PROMPT_PATH = (
    PROJECT_ROOT / "prompts" / "native_tool_terminal_summary_coverage_v8.md"
)
TERMINAL_SUMMARY_VERSION = "1.5.6-h3-terminal-summary-coverage-v8"
REQUIRED_IDS_MARKER = "{{REQUIRED_FACT_IDS}}"


def project_terminal_context_v8(
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
    "TERMINAL_SUMMARY_PROMPT_PATH",
    "TERMINAL_SUMMARY_VERSION",
    "project_terminal_context_v8",
]
