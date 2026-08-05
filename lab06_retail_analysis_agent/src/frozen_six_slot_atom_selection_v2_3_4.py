"""V2.3.4: program-frozen report slots with model-selected FACT atoms.

The program owns the six-section structure and admissibility rules.  The model
may only assign existing atom IDs to those slots; it cannot author structure,
values, calculations, bundle provenance, or report prose in this phase.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.claim_evidence_bundles_v2_3_2 import (
    BundleKind,
    ClaimEvidenceEnvelopeV2_3_2,
    ClaimSupportAtomV2_3_2,
    SemanticRole,
    reference_catalog,
)
from src.fact_schema import FactMetric
from src.report_validation import REPORT_SECTION_ORDER, ReportEvidenceReference


SELECTION_INSTRUCTION = (
    "Return one JSON object containing exactly the six supplied slot_id values "
    "in the supplied order. "
    "For each slot return only slot_id and atom_ids. Select only allowed atom "
    "IDs, include every per-slot required atom, and assign every global required "
    "atom exactly once across slots SLOT-002 through SLOT-005. Do not add section names, bundle "
    "IDs, claim modes, prose, business values, calculations, or tool calls."
)
FINAL_INSTRUCTION = (
    "Write exactly one report section for each validated frozen slot, in order. "
    "Use only that slot's support atoms and copy its complete allowed evidence "
    "objects into the local claim. Every number, date, rank, selection limit, "
    "and superlative must be directly supported. Do not output slot, bundle, or "
    "atom IDs and do not calculate new values. Evidence in each report section "
    "must be a subset of that section's slot allowed_evidence; never borrow from "
    "another slot. A slot without atoms must use a numeric-free bounded statement. "
    "A call_id is allowed only in chart_requests.call_id, never in report prose or titles."
)


class StrictV234Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class AtomDescriptorV2_3_4(StrictV234Model):
    atom_id: str = Field(pattern=r"^ATOM-\d{3,}$")
    semantic_role: SemanticRole
    display_value: str
    bundle_kind: BundleKind


class FrozenSlotCatalogEntryV2_3_4(StrictV234Model):
    slot_id: str = Field(pattern=r"^SLOT-00[1-6]$")
    section_name: str
    allowed_atom_ids: list[str]
    required_atom_ids: list[str]

    @model_validator(mode="after")
    def validate_required_subset(self) -> "FrozenSlotCatalogEntryV2_3_4":
        if len(self.allowed_atom_ids) != len(set(self.allowed_atom_ids)):
            raise ValueError("allowed atom IDs must be unique")
        if len(self.required_atom_ids) != len(set(self.required_atom_ids)):
            raise ValueError("required atom IDs must be unique")
        if not set(self.required_atom_ids).issubset(self.allowed_atom_ids):
            raise ValueError("required atoms must be allowed in the same slot")
        return self


class FrozenSlotCatalogEnvelopeV2_3_4(StrictV234Model):
    phase: Literal["frozen_six_slot_atom_catalog"]
    session_id: str = Field(pattern=r"^SESSION-[A-Za-z0-9_-]+$")
    turn_id: str = Field(pattern=r"^TURN-\d{3,}$")
    slots: list[FrozenSlotCatalogEntryV2_3_4] = Field(min_length=6, max_length=6)
    atom_catalog: list[AtomDescriptorV2_3_4]
    global_required_atom_ids: list[str]
    instruction: Literal[
        "Return one JSON object containing exactly the six supplied slot_id values "
        "in the supplied order. "
        "For each slot return only slot_id and atom_ids. Select only allowed atom "
        "IDs, include every per-slot required atom, and assign every global required "
        "atom exactly once across slots SLOT-002 through SLOT-005. Do not add section names, bundle "
        "IDs, claim modes, prose, business values, calculations, or tool calls."
    ] = SELECTION_INSTRUCTION

    @model_validator(mode="after")
    def validate_frozen_layout(self) -> "FrozenSlotCatalogEnvelopeV2_3_4":
        if [item.slot_id for item in self.slots] != [f"SLOT-{i:03d}" for i in range(1, 7)]:
            raise ValueError("catalog must contain the six frozen slot IDs in order")
        if [item.section_name for item in self.slots] != list(REPORT_SECTION_ORDER):
            raise ValueError("catalog section names must match the frozen report order")
        atom_ids = [item.atom_id for item in self.atom_catalog]
        if len(atom_ids) != len(set(atom_ids)):
            raise ValueError("catalog atom IDs must be unique")
        if not set(self.global_required_atom_ids).issubset(atom_ids):
            raise ValueError("global required atoms must exist in the catalog")
        return self


class FrozenSlotAtomSelectionV2_3_4(StrictV234Model):
    slot_id: str = Field(pattern=r"^SLOT-00[1-6]$")
    atom_ids: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("atom_ids")
    @classmethod
    def unique_atoms(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("selected atom IDs must be unique within a slot")
        return value


class FrozenSlotAtomSelectionDraftV2_3_4(StrictV234Model):
    phase: Literal["frozen_six_slot_atom_selection"]
    session_id: str = Field(pattern=r"^SESSION-[A-Za-z0-9_-]+$")
    turn_id: str = Field(pattern=r"^TURN-\d{3,}$")
    selections: list[FrozenSlotAtomSelectionV2_3_4] = Field(min_length=6, max_length=6)

    @model_validator(mode="after")
    def validate_selection_layout(self) -> "FrozenSlotAtomSelectionDraftV2_3_4":
        expected = [f"SLOT-{i:03d}" for i in range(1, 7)]
        if [item.slot_id for item in self.selections] != expected:
            raise ValueError("selection must return all six frozen slot IDs in order")
        return self


class AllowedChartSourceV2_3_4(StrictV234Model):
    call_id: str = Field(pattern=r"^CALL-\d{3,}$")
    tool_name: str = Field(min_length=1, max_length=100)


class ValidatedFrozenSlotV2_3_4(StrictV234Model):
    slot_id: str
    section_name: str
    selected_atom_ids: list[str]
    support_atoms: list[ClaimSupportAtomV2_3_2]
    allowed_evidence: list[ReportEvidenceReference]
    allowed_selection_limit_values: list[str]
    allowed_superlative_metrics: list[FactMetric]
    prohibited_inferences: list[str]


class ValidatedFrozenSlotEnvelopeV2_3_4(StrictV234Model):
    phase: Literal["report_terminal_validated_frozen_slots"]
    session_id: str
    turn_id: str
    slots: list[ValidatedFrozenSlotV2_3_4] = Field(min_length=6, max_length=6)
    allowed_chart_sources: list[AllowedChartSourceV2_3_4]
    instruction: Literal[
        "Write exactly one report section for each validated frozen slot, in order. "
        "Use only that slot's support atoms and copy its complete allowed evidence "
        "objects into the local claim. Every number, date, rank, selection limit, "
        "and superlative must be directly supported. Do not output slot, bundle, or "
        "atom IDs and do not calculate new values. Evidence in each report section "
        "must be a subset of that section's slot allowed_evidence; never borrow from "
        "another slot. A slot without atoms must use a numeric-free bounded statement. "
        "A call_id is allowed only in chart_requests.call_id, never in report prose or titles."
    ] = FINAL_INSTRUCTION


class FrozenSlotSelectionValidationError(ValueError):
    """Raised before final report generation when atom assignment drifts."""


def build_frozen_slot_catalog(
    source: ClaimEvidenceEnvelopeV2_3_2,
) -> FrozenSlotCatalogEnvelopeV2_3_4:
    atom_rows = [
        (atom, bundle.bundle_kind)
        for bundle in source.claim_evidence_bundles
        for atom in bundle.support_atoms
    ]
    scope_ids = [
        atom.atom_id for atom, kind in atom_rows
        if kind in {"request_parameter", "selection_limit"}
    ]
    policy_ids = [atom.atom_id for atom, kind in atom_rows if kind == "policy_boundary"]
    factual_ids = [
        atom.atom_id for atom, kind in atom_rows
        if kind not in {"request_parameter", "selection_limit", "policy_boundary"}
    ]
    slots = [
        FrozenSlotCatalogEntryV2_3_4(
            slot_id="SLOT-001", section_name=REPORT_SECTION_ORDER[0],
            allowed_atom_ids=scope_ids, required_atom_ids=scope_ids,
        ),
        *[
            FrozenSlotCatalogEntryV2_3_4(
                slot_id=f"SLOT-{index:03d}", section_name=REPORT_SECTION_ORDER[index - 1],
                allowed_atom_ids=scope_ids + factual_ids, required_atom_ids=[],
            )
            for index in range(2, 6)
        ],
        FrozenSlotCatalogEntryV2_3_4(
            slot_id="SLOT-006", section_name=REPORT_SECTION_ORDER[5],
            allowed_atom_ids=policy_ids, required_atom_ids=policy_ids,
        ),
    ]
    return FrozenSlotCatalogEnvelopeV2_3_4(
        phase="frozen_six_slot_atom_catalog",
        session_id=source.session_id,
        turn_id=source.turn_id,
        slots=slots,
        atom_catalog=[
            AtomDescriptorV2_3_4(
                atom_id=atom.atom_id,
                semantic_role=atom.semantic_role,
                display_value=atom.display_value,
                bundle_kind=kind,
            )
            for atom, kind in atom_rows
        ],
        global_required_atom_ids=factual_ids,
    )


def validate_frozen_slot_selection(
    draft: FrozenSlotAtomSelectionDraftV2_3_4,
    catalog: FrozenSlotCatalogEnvelopeV2_3_4,
    source: ClaimEvidenceEnvelopeV2_3_2,
) -> ValidatedFrozenSlotEnvelopeV2_3_4:
    if (draft.session_id, draft.turn_id) != (catalog.session_id, catalog.turn_id):
        raise FrozenSlotSelectionValidationError("selection crosses catalog session or turn")
    if (draft.session_id, draft.turn_id) != (source.session_id, source.turn_id):
        raise FrozenSlotSelectionValidationError("selection crosses evidence session or turn")
    atom_by_id = {
        atom.atom_id: atom
        for bundle in source.claim_evidence_bundles
        for atom in bundle.support_atoms
    }
    atom_to_bundle = {
        atom.atom_id: bundle
        for bundle in source.claim_evidence_bundles
        for atom in bundle.support_atoms
    }
    evidence_by_id = reference_catalog(source)
    validated: list[ValidatedFrozenSlotV2_3_4] = []
    selected_by_slot: dict[str, set[str]] = {}
    for selection, rule in zip(draft.selections, catalog.slots):
        selected = set(selection.atom_ids)
        allowed = set(rule.allowed_atom_ids)
        required = set(rule.required_atom_ids)
        if not selected.issubset(allowed):
            raise FrozenSlotSelectionValidationError(
                f"{selection.slot_id} contains an atom outside its whitelist"
            )
        if not required.issubset(selected):
            raise FrozenSlotSelectionValidationError(
                f"{selection.slot_id} omits a required atom"
            )
        selected_by_slot[selection.slot_id] = selected
        atoms = [atom_by_id[item] for item in selection.atom_ids]
        evidence_ids = list(dict.fromkeys(
            evidence_id for atom in atoms for evidence_id in atom.evidence_ids
        ))
        evidence = [evidence_by_id[item] for item in evidence_ids]
        selection_values = list(dict.fromkeys(
            atom.value for atom in atoms if atom.semantic_role == "selection_limit"
        ))
        superlative_metrics = list(dict.fromkeys(
            item.metric for item in evidence
            if getattr(item, "evidence_type", None) == "FACT"
            and getattr(item, "rank", None) == 1
            and getattr(item, "metric", None) is not None
        ))
        prohibited = list(dict.fromkeys(
            text for atom_id in selection.atom_ids
            for text in atom_to_bundle[atom_id].prohibited_inferences
        ))
        validated.append(ValidatedFrozenSlotV2_3_4(
            slot_id=selection.slot_id,
            section_name=rule.section_name,
            selected_atom_ids=selection.atom_ids,
            support_atoms=atoms,
            allowed_evidence=evidence,
            allowed_selection_limit_values=selection_values,
            allowed_superlative_metrics=superlative_metrics,
            prohibited_inferences=prohibited,
        ))
    factual_assignments = [
        atom_id
        for index in range(2, 6)
        for atom_id in selected_by_slot[f"SLOT-{index:03d}"]
        if atom_id in set(catalog.global_required_atom_ids)
    ]
    if set(factual_assignments) != set(catalog.global_required_atom_ids):
        raise FrozenSlotSelectionValidationError(
            "slots SLOT-002 through SLOT-005 do not cover every required factual atom"
        )
    if len(factual_assignments) != len(set(factual_assignments)):
        raise FrozenSlotSelectionValidationError(
            "each required factual atom must be assigned to exactly one report slot"
        )
    return ValidatedFrozenSlotEnvelopeV2_3_4(
        phase="report_terminal_validated_frozen_slots",
        session_id=draft.session_id,
        turn_id=draft.turn_id,
        slots=validated,
        allowed_chart_sources=[
            AllowedChartSourceV2_3_4(
                call_id=item.internal_call_id,
                tool_name=item.tool_name,
            )
            for item in source.tool_evidence
        ],
    )


__all__ = [
    "AtomDescriptorV2_3_4", "FrozenSlotAtomSelectionDraftV2_3_4",
    "FrozenSlotAtomSelectionV2_3_4", "FrozenSlotCatalogEnvelopeV2_3_4",
    "FrozenSlotCatalogEntryV2_3_4", "FrozenSlotSelectionValidationError",
    "ValidatedFrozenSlotEnvelopeV2_3_4", "ValidatedFrozenSlotV2_3_4",
    "build_frozen_slot_catalog", "validate_frozen_slot_selection",
]
