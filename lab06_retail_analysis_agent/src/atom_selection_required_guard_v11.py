"""Build an explicit required-atom copy map for model atom selection."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ATOM_SELECTION_REQUIRED_GUARD_PATH = (
    PROJECT_ROOT / "prompts" / "native_tool_atom_selection_required_guard_v11.md"
)
ATOM_SELECTION_REQUIRED_GUARD_VERSION = (
    "1.5.6-h3-atom-selection-required-guard-v11"
)
REQUIRED_ATOM_MAP_MARKER = "{{REQUIRED_ATOM_MAP}}"


def build_atom_selection_instruction_v11(catalog: Any) -> str:
    required_map = {
        rule.slot_id: list(rule.required_atom_ids)
        for rule in catalog.slots
        if rule.required_atom_ids
    }
    template = ATOM_SELECTION_REQUIRED_GUARD_PATH.read_text(
        encoding="utf-8"
    ).strip()
    return template.replace(
        REQUIRED_ATOM_MAP_MARKER,
        json.dumps(required_map, ensure_ascii=False, separators=(",", ":")),
    )


__all__ = [
    "ATOM_SELECTION_REQUIRED_GUARD_PATH",
    "ATOM_SELECTION_REQUIRED_GUARD_VERSION",
    "build_atom_selection_instruction_v11",
]
