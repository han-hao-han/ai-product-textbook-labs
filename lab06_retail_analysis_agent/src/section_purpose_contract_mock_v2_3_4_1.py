"""Deterministic doubles for the V2.3.4.1 section-purpose boundary."""

from __future__ import annotations

from src.frozen_six_slot_atom_selection_mock_v2_3_4 import mock_model_final_report
from src.section_purpose_contract_v2_3_4_1 import (
    SectionPurposeAtomSelectionV2_3_4_1,
    SectionPurposeCatalogV2_3_4_1,
    SectionPurposeSelectionDraftV2_3_4_1,
)


def mock_model_section_purpose_selection(
    catalog: SectionPurposeCatalogV2_3_4_1,
) -> SectionPurposeSelectionDraftV2_3_4_1:
    return SectionPurposeSelectionDraftV2_3_4_1(
        phase="section_purpose_atom_selection",
        session_id=catalog.session_id,
        turn_id=catalog.turn_id,
        selections=[SectionPurposeAtomSelectionV2_3_4_1(
            slot_id=rule.slot_id, atom_ids=list(rule.required_atom_ids)
        ) for rule in catalog.slots],
    )


__all__ = ["mock_model_section_purpose_selection", "mock_model_final_report"]
