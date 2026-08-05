"""Versioned final-envelope coverage guidance without Schema changes."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from src.report_terminal_protocol_guard_v2_3_4_2 import (
    IsolatedTerminalContextV2_3_4_2,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TERMINAL_COVERAGE_PROMPT_PATH = (
    PROJECT_ROOT / "prompts" / "native_tool_terminal_coverage_v6.md"
)
TERMINAL_COVERAGE_VERSION = "1.5.6-h3-terminal-coverage-v6"


def project_terminal_context_v6(
    context: IsolatedTerminalContextV2_3_4_2,
) -> IsolatedTerminalContextV2_3_4_2:
    instruction = TERMINAL_COVERAGE_PROMPT_PATH.read_text(
        encoding="utf-8"
    ).strip()
    visible = context.model_visible.model_copy(
        update={"instruction": instruction}
    )
    return replace(context, model_visible=visible)


__all__ = [
    "TERMINAL_COVERAGE_PROMPT_PATH",
    "TERMINAL_COVERAGE_VERSION",
    "project_terminal_context_v6",
]
