"""V2.3.4.1 six-slot purpose and evidence-type contract.

The model still selects atom IDs.  The program freezes section purpose,
admissible evidence kinds, complete-group selection, and required coverage.
It does not author business claims or calculate values.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.claim_evidence_bundles_v2_3_2 import (
    BundleKind, ClaimEvidenceEnvelopeV2_3_2, ClaimSupportAtomV2_3_2,
    reference_catalog,
)
from src.fact_schema import FactMetric
from src.frozen_six_slot_atom_selection_v2_3_4 import (
    AllowedChartSourceV2_3_4, AtomDescriptorV2_3_4,
)
from src.report_validation import REPORT_SECTION_ORDER, ReportEvidenceReference


SELECTION_INSTRUCTION = (
    "Return one JSON object with exactly the six supplied slot_id values in "
    "order. Each selection may contain only slot_id and atom_ids. Include every "
    "required atom. When selecting any atom_group, select every atom in that "
    "group. Keep optional selections within each slot limit. Use the section "
    "purpose and allowed claim intents to choose optional evidence. Do not add "
    "section names, group IDs, bundle IDs, prose, values, calculations, or tools."
)
FINAL_INSTRUCTION = (
    "Write exactly one ordered report section for each validated slot. Follow "
    "that slot's section_purpose, allowed_claim_intents, and prohibited_claim_intents. "
    "Every claim may use only its slot's allowed_evidence and must copy complete "
    "local reference objects. Never borrow evidence across slots or calculate new "
    "values. Empty-evidence claims must contain no numbers, dates, ranks, metrics, "
    "or named entities. A call_id is allowed only in chart_requests.call_id, never "
    "in report prose or titles. Do not output slot, group, bundle, or atom IDs."
)


class StrictPurposeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class AtomGroupV2_3_4_1(StrictPurposeModel):
    group_id: str = Field(pattern=r"^GROUP-\d{3,}$")
    bundle_kind: BundleKind
    atom_ids: list[str] = Field(min_length=1, max_length=40)


class SectionPurposeSlotRuleV2_3_4_1(StrictPurposeModel):
    slot_id: str = Field(pattern=r"^SLOT-00[1-6]$")
    section_name: str
    section_purpose: str = Field(min_length=1, max_length=500)
    allowed_bundle_kinds: list[BundleKind]
    allowed_atom_ids: list[str]
    required_atom_ids: list[str]
    optional_atom_limit: int = Field(ge=0, le=40)
    allowed_claim_intents: list[str]
    prohibited_claim_intents: list[str]

    @model_validator(mode="after")
    def validate_rule(self) -> "SectionPurposeSlotRuleV2_3_4_1":
        if not set(self.required_atom_ids).issubset(self.allowed_atom_ids):
            raise ValueError("required atoms must be allowed by the slot")
        for values in (
            self.allowed_bundle_kinds, self.allowed_atom_ids,
            self.required_atom_ids, self.allowed_claim_intents,
            self.prohibited_claim_intents,
        ):
            if len(values) != len(set(values)):
                raise ValueError("section-purpose contract lists must be unique")
        return self


class SectionPurposeCatalogV2_3_4_1(StrictPurposeModel):
    request_type: Literal["frozen_six_slot_section_purpose_catalog"]
    session_id: str = Field(pattern=r"^SESSION-[A-Za-z0-9_-]+$")
    turn_id: str = Field(pattern=r"^TURN-\d{3,}$")
    slots: list[SectionPurposeSlotRuleV2_3_4_1] = Field(min_length=6, max_length=6)
    atom_catalog: list[AtomDescriptorV2_3_4]
    atom_groups: list[AtomGroupV2_3_4_1]
    instruction: Literal[
        "Return one JSON object with exactly the six supplied slot_id values in "
        "order. Each selection may contain only slot_id and atom_ids. Include every "
        "required atom. When selecting any atom_group, select every atom in that "
        "group. Keep optional selections within each slot limit. Use the section "
        "purpose and allowed claim intents to choose optional evidence. Do not add "
        "section names, group IDs, bundle IDs, prose, values, calculations, or tools."
    ] = SELECTION_INSTRUCTION

    @model_validator(mode="after")
    def validate_layout(self) -> "SectionPurposeCatalogV2_3_4_1":
        if [item.slot_id for item in self.slots] != [f"SLOT-{i:03d}" for i in range(1, 7)]:
            raise ValueError("purpose catalog must contain six frozen slots in order")
        if [item.section_name for item in self.slots] != list(REPORT_SECTION_ORDER):
            raise ValueError("purpose catalog sections differ from frozen report order")
        atom_ids = [item.atom_id for item in self.atom_catalog]
        grouped = [atom_id for group in self.atom_groups for atom_id in group.atom_ids]
        if len(atom_ids) != len(set(atom_ids)) or set(grouped) != set(atom_ids):
            raise ValueError("atom groups must partition the atom catalog")
        if len(grouped) != len(set(grouped)):
            raise ValueError("an atom may belong to only one group")
        return self


class SectionPurposeAtomSelectionV2_3_4_1(StrictPurposeModel):
    slot_id: str = Field(pattern=r"^SLOT-00[1-6]$")
    atom_ids: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("atom_ids")
    @classmethod
    def unique_atoms(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("selected atom IDs must be unique within a slot")
        return value


class SectionPurposeSelectionDraftV2_3_4_1(StrictPurposeModel):
    phase: Literal["section_purpose_atom_selection"]
    session_id: str = Field(pattern=r"^SESSION-[A-Za-z0-9_-]+$")
    turn_id: str = Field(pattern=r"^TURN-\d{3,}$")
    selections: list[SectionPurposeAtomSelectionV2_3_4_1] = Field(min_length=6, max_length=6)

    @model_validator(mode="after")
    def validate_layout(self) -> "SectionPurposeSelectionDraftV2_3_4_1":
        expected = [f"SLOT-{i:03d}" for i in range(1, 7)]
        if [item.slot_id for item in self.selections] != expected:
            raise ValueError("selection must return all six frozen slots in order")
        return self


class ValidatedPurposeSlotV2_3_4_1(StrictPurposeModel):
    slot_id: str
    section_name: str
    section_purpose: str
    allowed_claim_intents: list[str]
    prohibited_claim_intents: list[str]
    selected_atom_ids: list[str]
    support_atoms: list[ClaimSupportAtomV2_3_2]
    allowed_evidence: list[ReportEvidenceReference]
    allowed_selection_limit_values: list[str]
    allowed_superlative_metrics: list[FactMetric]
    prohibited_inferences: list[str]


class ValidatedSectionPurposeEnvelopeV2_3_4_1(StrictPurposeModel):
    phase: Literal["report_terminal_validated_section_purpose_slots"]
    session_id: str
    turn_id: str
    slots: list[ValidatedPurposeSlotV2_3_4_1] = Field(min_length=6, max_length=6)
    allowed_chart_sources: list[AllowedChartSourceV2_3_4]
    instruction: Literal[
        "Write exactly one ordered report section for each validated slot. Follow "
        "that slot's section_purpose, allowed_claim_intents, and prohibited_claim_intents. "
        "Every claim may use only its slot's allowed_evidence and must copy complete "
        "local reference objects. Never borrow evidence across slots or calculate new "
        "values. Empty-evidence claims must contain no numbers, dates, ranks, metrics, "
        "or named entities. A call_id is allowed only in chart_requests.call_id, never "
        "in report prose or titles. Do not output slot, group, bundle, or atom IDs."
    ] = FINAL_INSTRUCTION


class SectionPurposeValidationError(ValueError):
    pass


def _atoms_by_kind(source: ClaimEvidenceEnvelopeV2_3_2) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for bundle in source.claim_evidence_bundles:
        result.setdefault(bundle.bundle_kind, []).extend(
            atom.atom_id for atom in bundle.support_atoms
        )
    return result


def build_section_purpose_catalog(
    source: ClaimEvidenceEnvelopeV2_3_2,
) -> SectionPurposeCatalogV2_3_4_1:
    by_kind = _atoms_by_kind(source)
    scope_kinds: list[BundleKind] = ["request_parameter", "selection_limit"]
    result_kinds: list[BundleKind] = [
        "ranked_entity", "aggregate_metric", "period_scope", "cross_tool_observation"
    ]
    policy_kinds: list[BundleKind] = ["policy_boundary"]
    scope_ids = [atom for kind in scope_kinds for atom in by_kind.get(kind, [])]
    result_ids = [atom for kind in result_kinds for atom in by_kind.get(kind, [])]
    policy_ids = [atom for kind in policy_kinds for atom in by_kind.get(kind, [])]
    representative_bundle = next(
        (
            bundle for bundle in source.claim_evidence_bundles
            if bundle.bundle_kind in result_kinds
        ),
        None,
    )
    representative_ids = (
        [atom.atom_id for atom in representative_bundle.support_atoms]
        if representative_bundle is not None else []
    )
    purposes = [
        (
            "Restate the validated business question, metric, period and selection scope.",
            ["request_scope", "metric_scope", "period_scope"],
            ["business_result", "causal_explanation", "recommendation"],
        ),
        (
            "Present the complete deterministic business result required by the question.",
            ["ranked_finding", "aggregate_finding", "cross_tool_finding"],
            ["causal_explanation", "forecast", "unsupported_recommendation"],
        ),
        (
            "Explain which deterministic tools and shared FACT data support the report and charts.",
            ["tool_method", "fact_provenance", "chart_description"],
            ["new_business_result", "causal_explanation", "forecast"],
        ),
        (
            "Offer cautious interpretation only where selected FACT groups support it.",
            ["bounded_interpretation", "anomaly_for_manual_review"],
            ["causality", "forecast", "statistical_significance_without_fact"],
        ),
        (
            "Give bounded actions for human review based only on selected FACT groups.",
            ["manual_review_action", "follow_up_analysis", "bounded_recommendation"],
            ["automatic_action", "forecast", "guaranteed_outcome", "causality"],
        ),
        (
            "State privacy, incomplete-period and historical-analysis boundaries.",
            ["policy_limit", "data_limit", "analysis_limit"],
            ["business_result", "recommendation", "weaken_policy"],
        ),
    ]
    rules = []
    for index, (purpose, allowed_intents, prohibited_intents) in enumerate(purposes, start=1):
        if index == 1:
            allowed_kinds, allowed_ids, required_ids, optional_limit = scope_kinds, scope_ids, scope_ids, 0
        elif index == 2:
            allowed_kinds, allowed_ids, required_ids, optional_limit = result_kinds, result_ids, result_ids, 0
        elif index == 3:
            allowed_kinds = scope_kinds + (
                [representative_bundle.bundle_kind] if representative_bundle is not None else []
            )
            allowed_ids, required_ids = scope_ids + representative_ids, []
            optional_limit = len(allowed_ids)
        elif index in {4, 5}:
            allowed_kinds = (
                [representative_bundle.bundle_kind] if representative_bundle is not None else []
            )
            allowed_ids, required_ids = representative_ids, []
            optional_limit = len(allowed_ids)
        else:
            allowed_kinds, allowed_ids, required_ids, optional_limit = policy_kinds, policy_ids, policy_ids, 0
        rules.append(SectionPurposeSlotRuleV2_3_4_1(
            slot_id=f"SLOT-{index:03d}", section_name=REPORT_SECTION_ORDER[index - 1],
            section_purpose=purpose, allowed_bundle_kinds=allowed_kinds,
            allowed_atom_ids=allowed_ids, required_atom_ids=required_ids,
            optional_atom_limit=optional_limit,
            allowed_claim_intents=allowed_intents,
            prohibited_claim_intents=prohibited_intents,
        ))
    atom_rows = [
        (atom, bundle.bundle_kind)
        for bundle in source.claim_evidence_bundles for atom in bundle.support_atoms
    ]
    return SectionPurposeCatalogV2_3_4_1(
        request_type="frozen_six_slot_section_purpose_catalog",
        session_id=source.session_id, turn_id=source.turn_id, slots=rules,
        atom_catalog=[AtomDescriptorV2_3_4(
            atom_id=atom.atom_id, semantic_role=atom.semantic_role,
            display_value=atom.display_value, bundle_kind=kind,
        ) for atom, kind in atom_rows],
        atom_groups=[AtomGroupV2_3_4_1(
            group_id=f"GROUP-{index:03d}", bundle_kind=bundle.bundle_kind,
            atom_ids=[atom.atom_id for atom in bundle.support_atoms],
        ) for index, bundle in enumerate(source.claim_evidence_bundles, start=1)],
    )


def validate_section_purpose_selection(
    draft: SectionPurposeSelectionDraftV2_3_4_1,
    catalog: SectionPurposeCatalogV2_3_4_1,
    source: ClaimEvidenceEnvelopeV2_3_2,
) -> ValidatedSectionPurposeEnvelopeV2_3_4_1:
    if (draft.session_id, draft.turn_id) != (catalog.session_id, catalog.turn_id):
        raise SectionPurposeValidationError("selection crosses catalog session or turn")
    if (draft.session_id, draft.turn_id) != (source.session_id, source.turn_id):
        raise SectionPurposeValidationError("selection crosses evidence session or turn")
    atom_by_id = {
        atom.atom_id: atom for bundle in source.claim_evidence_bundles
        for atom in bundle.support_atoms
    }
    atom_to_bundle = {
        atom.atom_id: bundle for bundle in source.claim_evidence_bundles
        for atom in bundle.support_atoms
    }
    evidence_by_id = reference_catalog(source)
    validated = []
    for selection, rule in zip(draft.selections, catalog.slots):
        selected = set(selection.atom_ids)
        required = set(rule.required_atom_ids)
        if not selected.issubset(rule.allowed_atom_ids):
            raise SectionPurposeValidationError(f"{selection.slot_id} contains disallowed evidence type")
        if not required.issubset(selected):
            raise SectionPurposeValidationError(f"{selection.slot_id} omits required purpose evidence")
        optional_count = len(selected - required)
        if optional_count > rule.optional_atom_limit:
            raise SectionPurposeValidationError(f"{selection.slot_id} exceeds optional evidence capacity")
        for group in catalog.atom_groups:
            group_ids = set(group.atom_ids)
            if selected & group_ids and not group_ids.issubset(selected):
                raise SectionPurposeValidationError(
                    f"{selection.slot_id} selects only part of {group.group_id}"
                )
        atoms = [atom_by_id[item] for item in selection.atom_ids]
        evidence_ids = list(dict.fromkeys(
            evidence_id for atom in atoms for evidence_id in atom.evidence_ids
        ))
        evidence = [evidence_by_id[item] for item in evidence_ids]
        metrics = list(dict.fromkeys(
            item.metric for item in evidence
            if getattr(item, "evidence_type", None) == "FACT"
            and getattr(item, "rank", None) == 1
            and getattr(item, "metric", None) is not None
        ))
        validated.append(ValidatedPurposeSlotV2_3_4_1(
            slot_id=selection.slot_id, section_name=rule.section_name,
            section_purpose=rule.section_purpose,
            allowed_claim_intents=rule.allowed_claim_intents,
            prohibited_claim_intents=rule.prohibited_claim_intents,
            selected_atom_ids=selection.atom_ids, support_atoms=atoms,
            allowed_evidence=evidence,
            allowed_selection_limit_values=list(dict.fromkeys(
                atom.value for atom in atoms if atom.semantic_role == "selection_limit"
            )),
            allowed_superlative_metrics=metrics,
            prohibited_inferences=list(dict.fromkeys(
                text for atom_id in selection.atom_ids
                for text in atom_to_bundle[atom_id].prohibited_inferences
            )),
        ))
    return ValidatedSectionPurposeEnvelopeV2_3_4_1(
        phase="report_terminal_validated_section_purpose_slots",
        session_id=draft.session_id, turn_id=draft.turn_id, slots=validated,
        allowed_chart_sources=[AllowedChartSourceV2_3_4(
            call_id=item.internal_call_id, tool_name=item.tool_name,
        ) for item in source.tool_evidence],
    )


__all__ = [
    "SectionPurposeCatalogV2_3_4_1", "SectionPurposeSelectionDraftV2_3_4_1",
    "SectionPurposeAtomSelectionV2_3_4_1", "SectionPurposeValidationError",
    "ValidatedSectionPurposeEnvelopeV2_3_4_1", "build_section_purpose_catalog",
    "validate_section_purpose_selection",
]
