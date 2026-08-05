"""V2.3.3 controlled claim planning without program-authored prose."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.claim_evidence_bundles_v2_3_2 import (
    ClaimEvidenceEnvelopeV2_3_2,
    ClaimSupportAtomV2_3_2,
    reference_catalog,
)
from src.fact_schema import FactMetric
from src.report_validation import (
    REPORT_SECTION_ORDER,
    ReportEvidenceReference,
    ReportSectionName,
)


ClaimMode = Literal[
    "request_scope",
    "ranked_observation",
    "aggregate_observation",
    "cross_tool_observation",
    "tool_method",
    "limited_interpretation",
    "advice",
    "policy_limit",
]

PLANNER_INSTRUCTION = (
    "Return only a controlled claim plan with at least one slot for each of "
    "the six exact section_name enum values in frozen order. Keep each slot "
    "small and select no more than twelve atom IDs. Select atom IDs only; "
    "bundle provenance and selection-limit permission are derived by the "
    "program. Do not write claim text, copy business values, "
    "calculate, translate section names, or call tools."
)
FINAL_INSTRUCTION = (
    "Write the final report using exactly the validated claim slots. Every "
    "number, date, rank, selection limit, and superlative must stay inside "
    "its slot and copy that slot's full allowed evidence references. Do not "
    "output slot, bundle, or atom IDs and do not calculate new values."
)


class StrictClaimPlanModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ClaimPlanSlotDraftV2_3_3(StrictClaimPlanModel):
    slot_id: str = Field(pattern=r"^SLOT-\d{3,}$")
    section_name: ReportSectionName
    claim_mode: ClaimMode
    atom_ids: list[str] = Field(default_factory=list, max_length=12)
    requested_superlative_metric: FactMetric | None = None

    @field_validator("atom_ids")
    @classmethod
    def unique_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("claim-plan IDs must be unique within a slot")
        return value


class ClaimPlanDraftV2_3_3(StrictClaimPlanModel):
    phase: Literal["controlled_claim_plan"]
    session_id: str = Field(pattern=r"^SESSION-[A-Za-z0-9_-]+$")
    turn_id: str = Field(pattern=r"^TURN-\d{3,}$")
    slots: list[ClaimPlanSlotDraftV2_3_3] = Field(min_length=6, max_length=72)

    @model_validator(mode="after")
    def validate_slots(self) -> "ClaimPlanDraftV2_3_3":
        slot_ids = [slot.slot_id for slot in self.slots]
        if len(slot_ids) != len(set(slot_ids)):
            raise ValueError("claim-plan slot IDs must be unique")
        section_positions = [
            REPORT_SECTION_ORDER.index(slot.section_name)
            if slot.section_name in REPORT_SECTION_ORDER
            else -1
            for slot in self.slots
        ]
        if -1 in section_positions:
            raise ValueError("claim-plan contains an unknown report section")
        if section_positions != sorted(section_positions):
            raise ValueError("claim-plan sections must follow frozen report order")
        if set(slot.section_name for slot in self.slots) != set(REPORT_SECTION_ORDER):
            raise ValueError("claim-plan must cover all six frozen report sections")
        return self


class ValidatedClaimSlotV2_3_3(StrictClaimPlanModel):
    slot_id: str = Field(pattern=r"^SLOT-\d{3,}$")
    section_name: str
    claim_mode: ClaimMode
    selected_bundle_ids: list[str]
    selected_atom_ids: list[str]
    support_atoms: list[ClaimSupportAtomV2_3_2]
    allowed_evidence: list[ReportEvidenceReference]
    allowed_selection_limit_values: list[str]
    allowed_superlative_metrics: list[FactMetric]
    prohibited_inferences: list[str]


class AllowedChartSourceV2_3_3(StrictClaimPlanModel):
    call_id: str = Field(pattern=r"^CALL-\d{3,}$")
    tool_name: str = Field(min_length=1, max_length=100)


class ValidatedClaimPlanEnvelopeV2_3_3(StrictClaimPlanModel):
    phase: Literal["report_terminal_validated_claim_plan"]
    session_id: str
    turn_id: str
    slots: list[ValidatedClaimSlotV2_3_3]
    allowed_chart_sources: list[AllowedChartSourceV2_3_3]
    instruction: Literal[
        "Write the final report using exactly the validated claim slots. Every "
        "number, date, rank, selection limit, and superlative must stay inside "
        "its slot and copy that slot's full allowed evidence references. Do not "
        "output slot, bundle, or atom IDs and do not calculate new values."
    ] = FINAL_INSTRUCTION


class ClaimPlanValidationError(ValueError):
    """Raised before final report generation when a controlled plan drifts."""


def _mode_constraints(slot: ClaimPlanSlotDraftV2_3_3, bundle_kinds: set[str]) -> None:
    if slot.claim_mode == "advice":
        if slot.section_name != REPORT_SECTION_ORDER[4]:
            raise ClaimPlanValidationError("advice belongs in the advice section")
        return
    if not slot.atom_ids:
        raise ClaimPlanValidationError("evidence-bearing claim slots cannot be empty")
    expected_kinds = {
        "request_scope": {"request_parameter"},
        "ranked_observation": {"ranked_entity"},
        "aggregate_observation": {"aggregate_metric", "period_scope"},
        "cross_tool_observation": {"cross_tool_observation"},
        "policy_limit": {"policy_boundary"},
    }.get(slot.claim_mode)
    if expected_kinds is not None and not (bundle_kinds & expected_kinds):
        raise ClaimPlanValidationError(f"{slot.claim_mode} selected incompatible bundle kinds")


def validate_claim_plan(
    draft: ClaimPlanDraftV2_3_3,
    source: ClaimEvidenceEnvelopeV2_3_2,
) -> ValidatedClaimPlanEnvelopeV2_3_3:
    if (draft.session_id, draft.turn_id) != (source.session_id, source.turn_id):
        raise ClaimPlanValidationError("claim plan crosses session or turn")
    bundle_by_id = {item.bundle_id: item for item in source.claim_evidence_bundles}
    atom_to_bundle = {
        atom.atom_id: bundle.bundle_id
        for bundle in source.claim_evidence_bundles
        for atom in bundle.support_atoms
    }
    atom_by_id = {
        atom.atom_id: atom
        for bundle in source.claim_evidence_bundles
        for atom in bundle.support_atoms
    }
    evidence_by_id = reference_catalog(source)
    validated: list[ValidatedClaimSlotV2_3_3] = []
    for slot in draft.slots:
        unknown_atoms = [item for item in slot.atom_ids if item not in atom_by_id]
        if unknown_atoms:
            raise ClaimPlanValidationError("claim plan references an unknown atom")
        selected_bundle_ids = list(
            dict.fromkeys(atom_to_bundle[item] for item in slot.atom_ids)
        )
        bundle_kinds = {
            bundle_by_id[item].bundle_kind for item in selected_bundle_ids
        }
        _mode_constraints(slot, bundle_kinds)
        atoms = [atom_by_id[item] for item in slot.atom_ids]
        selection_values = list(
            dict.fromkeys(atom.value for atom in atoms if atom.semantic_role == "selection_limit")
        )
        evidence_ids = list(
            dict.fromkeys(evidence_id for atom in atoms for evidence_id in atom.evidence_ids)
        )
        evidence = [evidence_by_id[item] for item in evidence_ids]
        rank_one_metrics = list(
            dict.fromkeys(
                item.metric
                for item in evidence
                if getattr(item, "evidence_type", None) == "FACT"
                and getattr(item, "rank", None) == 1
                and getattr(item, "metric", None) is not None
            )
        )
        if (
            slot.requested_superlative_metric is not None
            and slot.requested_superlative_metric not in rank_one_metrics
        ):
            raise ClaimPlanValidationError(
                "superlative intent lacks a matching rank=1 metric FACT"
            )
        prohibited = list(
            dict.fromkeys(
                item
                for bundle_id in selected_bundle_ids
                for item in bundle_by_id[bundle_id].prohibited_inferences
            )
        )
        validated.append(
            ValidatedClaimSlotV2_3_3(
                slot_id=slot.slot_id,
                section_name=slot.section_name,
                claim_mode=slot.claim_mode,
                selected_bundle_ids=selected_bundle_ids,
                selected_atom_ids=slot.atom_ids,
                support_atoms=atoms,
                allowed_evidence=evidence,
                allowed_selection_limit_values=selection_values,
                allowed_superlative_metrics=(
                    []
                    if slot.requested_superlative_metric is None
                    else [slot.requested_superlative_metric]
                ),
                prohibited_inferences=prohibited,
            )
        )
    return ValidatedClaimPlanEnvelopeV2_3_3(
        phase="report_terminal_validated_claim_plan",
        session_id=draft.session_id,
        turn_id=draft.turn_id,
        slots=validated,
        allowed_chart_sources=[
            AllowedChartSourceV2_3_3(
                call_id=item.internal_call_id,
                tool_name=item.tool_name,
            )
            for item in source.tool_evidence
        ],
    )


__all__ = [
    "ClaimPlanDraftV2_3_3",
    "ClaimPlanSlotDraftV2_3_3",
    "ClaimPlanValidationError",
    "AllowedChartSourceV2_3_3",
    "ValidatedClaimPlanEnvelopeV2_3_3",
    "ValidatedClaimSlotV2_3_3",
    "validate_claim_plan",
]
