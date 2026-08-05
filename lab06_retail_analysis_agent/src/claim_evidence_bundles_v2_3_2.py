"""Deterministic, non-authoring claim evidence bundles for V2.3.2."""

from __future__ import annotations

import calendar
import re
from collections import defaultdict
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.fact_schema import FactDimension
from src.report_admissible_evidence_projection_v2_3_1 import (
    ReportAdmissibleEnvelopeV2_3_1,
    ReportAdmissibleToolEvidenceV2_3_1,
)
from src.report_validation import (
    ReportFactReference,
    ReportPolicyReference,
    ReportRequestReference,
)


BundleKind = Literal[
    "selection_limit",
    "ranked_entity",
    "aggregate_metric",
    "period_scope",
    "request_parameter",
    "policy_boundary",
    "cross_tool_observation",
]
SemanticRole = Literal[
    "selection_limit",
    "entity_rank",
    "entity_identity",
    "metric_value",
    "period",
    "request_parameter",
    "policy_boundary",
]
EvidenceId = str
EVIDENCE_ID_PATTERN = re.compile(r"^(?:FACT|REQUEST|POLICY)-\d{3,}$")
V2_3_2_INSTRUCTION = (
    "Return exactly one final control-response JSON object. Evidence bundles "
    "are planning aids only: for every semantic atom used in a claim, copy "
    "the listed full reference objects from tool_evidence into that same "
    "claim. Never output bundle IDs or calculate new values."
)


class StrictBundleModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ClaimBundleSubjectV2_3_2(StrictBundleModel):
    rank: int | None = Field(default=None, ge=1)
    dimensions: list[FactDimension] = Field(default_factory=list)
    period: str | None = None
    start_date: str | None = None
    end_date: str | None = None


class ClaimSupportAtomV2_3_2(StrictBundleModel):
    atom_id: str = Field(pattern=r"^ATOM-\d{3,}$")
    semantic_role: SemanticRole
    value: str = Field(min_length=1, max_length=500)
    display_value: str = Field(min_length=1, max_length=500)
    evidence_ids: list[EvidenceId] = Field(min_length=1, max_length=20)

    @field_validator("evidence_ids")
    @classmethod
    def validate_evidence_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("support atom evidence IDs must be unique")
        if any(EVIDENCE_ID_PATTERN.fullmatch(item) is None for item in value):
            raise ValueError("support atom contains an invalid evidence ID")
        return value


class ClaimEvidenceBundleV2_3_2(StrictBundleModel):
    bundle_id: str = Field(pattern=r"^BUNDLE-\d{3,}$")
    bundle_kind: BundleKind
    source_call_ids: list[str] = Field(min_length=1, max_length=7)
    source_tool_names: list[str] = Field(min_length=1, max_length=7)
    subject: ClaimBundleSubjectV2_3_2
    support_atoms: list[ClaimSupportAtomV2_3_2] = Field(
        min_length=1, max_length=30
    )
    prohibited_inferences: list[str] = Field(min_length=1, max_length=10)

    @field_validator("source_call_ids")
    @classmethod
    def validate_call_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)) or any(
            re.fullmatch(r"CALL-\d{3,}", item) is None for item in value
        ):
            raise ValueError("bundle call IDs must be unique valid IDs")
        return value

    @field_validator("source_tool_names", "prohibited_inferences")
    @classmethod
    def validate_unique_text(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)) or any(not item.strip() for item in value):
            raise ValueError("bundle text lists must be non-empty and unique")
        return value


class BundleUsageContractV2_3_2(StrictBundleModel):
    model_chooses_supported_claims: Literal[True] = True
    combined_claim_uses_union_of_atom_evidence: Literal[True] = True
    repeated_number_repeats_local_evidence: Literal[True] = True
    cross_claim_evidence_borrowing_allowed: Literal[False] = False
    bundle_ids_allowed_in_report: Literal[False] = False
    model_arithmetic_allowed: Literal[False] = False
    post_hoc_evidence_injection_allowed: Literal[False] = False


class ClaimEvidenceEnvelopeV2_3_2(StrictBundleModel):
    phase: Literal["report_terminal_claim_evidence_bundles"]
    session_id: str = Field(pattern=r"^SESSION-[A-Za-z0-9_-]+$")
    turn_id: str = Field(pattern=r"^TURN-\d{3,}$")
    tool_evidence: list[ReportAdmissibleToolEvidenceV2_3_1] = Field(
        min_length=1
    )
    claim_evidence_bundles: list[ClaimEvidenceBundleV2_3_2] = Field(
        min_length=1, max_length=100
    )
    bundle_usage_contract: BundleUsageContractV2_3_2
    instruction: Literal[
        "Return exactly one final control-response JSON object. Evidence "
        "bundles are planning aids only: for every semantic atom used in a "
        "claim, copy the listed full reference objects from tool_evidence "
        "into that same claim. Never output bundle IDs or calculate new values."
    ] = V2_3_2_INSTRUCTION

    @model_validator(mode="after")
    def validate_bundle_references(self) -> "ClaimEvidenceEnvelopeV2_3_2":
        evidence_ids: set[str] = set()
        calls: dict[str, str] = {}
        for call in self.tool_evidence:
            calls[call.internal_call_id] = call.tool_name
            evidence_ids.update(item.fact_id for item in call.fact_references)
            evidence_ids.update(
                item.request_id for item in call.request_references
            )
            evidence_ids.update(item.policy_id for item in call.policy_references)
        bundle_ids = [item.bundle_id for item in self.claim_evidence_bundles]
        atom_ids = [
            atom.atom_id
            for bundle in self.claim_evidence_bundles
            for atom in bundle.support_atoms
        ]
        if len(bundle_ids) != len(set(bundle_ids)):
            raise ValueError("bundle IDs must be unique")
        if len(atom_ids) != len(set(atom_ids)):
            raise ValueError("atom IDs must be unique")
        for bundle in self.claim_evidence_bundles:
            if any(call_id not in calls for call_id in bundle.source_call_ids):
                raise ValueError("bundle references an unknown call ID")
            expected_tools = list(
                dict.fromkeys(calls[item] for item in bundle.source_call_ids)
            )
            if bundle.source_tool_names != expected_tools:
                raise ValueError("bundle call and tool provenance disagree")
            for atom in bundle.support_atoms:
                if any(item not in evidence_ids for item in atom.evidence_ids):
                    raise ValueError("bundle references unknown evidence")
        return self


class _BundleBuilder:
    def __init__(self) -> None:
        self.bundles: list[ClaimEvidenceBundleV2_3_2] = []
        self.bundle_index = 0
        self.atom_index = 0

    def atom(
        self,
        *,
        semantic_role: SemanticRole,
        value: str,
        display_value: str,
        evidence_ids: list[str],
    ) -> ClaimSupportAtomV2_3_2:
        self.atom_index += 1
        return ClaimSupportAtomV2_3_2(
            atom_id=f"ATOM-{self.atom_index:03d}",
            semantic_role=semantic_role,
            value=value,
            display_value=display_value,
            evidence_ids=list(dict.fromkeys(evidence_ids)),
        )

    def add(
        self,
        *,
        bundle_kind: BundleKind,
        calls: list[ReportAdmissibleToolEvidenceV2_3_1],
        subject: ClaimBundleSubjectV2_3_2,
        atoms: list[ClaimSupportAtomV2_3_2],
        prohibited: list[str],
    ) -> None:
        self.bundle_index += 1
        self.bundles.append(
            ClaimEvidenceBundleV2_3_2(
                bundle_id=f"BUNDLE-{self.bundle_index:03d}",
                bundle_kind=bundle_kind,
                source_call_ids=[item.internal_call_id for item in calls],
                source_tool_names=list(
                    dict.fromkeys(item.tool_name for item in calls)
                ),
                subject=subject,
                support_atoms=atoms,
                prohibited_inferences=prohibited,
            )
        )


def _subject(reference: ReportFactReference) -> ClaimBundleSubjectV2_3_2:
    return ClaimBundleSubjectV2_3_2(
        rank=reference.rank,
        dimensions=reference.dimensions,
        period=reference.period,
        start_date=reference.start_date,
        end_date=reference.end_date,
    )


def _same_entity_scope(
    left: ReportFactReference,
    right: ReportFactReference,
) -> bool:
    return (
        left.dimensions == right.dimensions
        and left.period == right.period
        and left.start_date == right.start_date
        and left.end_date == right.end_date
    )


def _unique_calls(
    calls: list[ReportAdmissibleToolEvidenceV2_3_1],
) -> list[ReportAdmissibleToolEvidenceV2_3_1]:
    return list({item.internal_call_id: item for item in calls}.values())


def _period_atom(
    builder: _BundleBuilder,
    reference: ReportFactReference,
) -> ClaimSupportAtomV2_3_2:
    values = [
        item
        for item in (
            reference.period,
            reference.start_date,
            reference.end_date,
        )
        if item is not None
    ]
    display = "至".join(values[1:]) if len(values) > 1 else values[0]
    return builder.atom(
        semantic_role="period",
        value="|".join(values),
        display_value=display,
        evidence_ids=[reference.fact_id],
    )


def build_claim_evidence_bundles(
    envelope: ReportAdmissibleEnvelopeV2_3_1,
) -> list[ClaimEvidenceBundleV2_3_2]:
    builder = _BundleBuilder()
    used_fact_ids: set[str] = set()
    request_sources: dict[str, list[ReportAdmissibleToolEvidenceV2_3_1]] = (
        defaultdict(list)
    )
    policy_sources: dict[str, list[ReportAdmissibleToolEvidenceV2_3_1]] = (
        defaultdict(list)
    )
    requests: dict[str, ReportRequestReference] = {}
    policies: dict[str, ReportPolicyReference] = {}

    for call in envelope.tool_evidence:
        facts = call.fact_references
        for reference in facts:
            if reference.metric != "top_n":
                continue
            builder.add(
                bundle_kind="selection_limit",
                calls=[call],
                subject=_subject(reference),
                atoms=[
                    builder.atom(
                        semantic_role="selection_limit",
                        value=reference.value,
                        display_value=reference.display_value,
                        evidence_ids=[reference.fact_id],
                    )
                ],
                prohibited=[
                    "Do not treat the selection limit as an entity rank.",
                    "Do not infer values outside the selected result set.",
                ],
            )
            used_fact_ids.add(reference.fact_id)

        anchors = [item for item in facts if item.rank is not None]
        for anchor in anchors:
            members = [
                item
                for item in facts
                if item.metric != "top_n"
                and _same_entity_scope(anchor, item)
                and item.fact_id not in used_fact_ids
            ]
            if not members:
                continue
            atoms = [
                builder.atom(
                    semantic_role="entity_rank",
                    value=str(anchor.rank),
                    display_value=f"第{anchor.rank}名",
                    evidence_ids=[anchor.fact_id],
                )
            ]
            atoms.extend(
                builder.atom(
                    semantic_role="entity_identity",
                    value=dimension.value,
                    display_value=dimension.value,
                    evidence_ids=[anchor.fact_id],
                )
                for dimension in anchor.dimensions
            )
            atoms.extend(
                builder.atom(
                    semantic_role="metric_value",
                    value=item.value,
                    display_value=item.display_value,
                    evidence_ids=[item.fact_id],
                )
                for item in members
            )
            atoms.append(_period_atom(builder, anchor))
            builder.add(
                bundle_kind="ranked_entity",
                calls=[call],
                subject=_subject(anchor),
                atoms=atoms,
                prohibited=[
                    "Do not infer profit, causality or future performance.",
                    "Do not compare unbundled entities or calculate shares.",
                ],
            )
            used_fact_ids.update(item.fact_id for item in members)

        for reference in facts:
            if reference.fact_id in used_fact_ids:
                continue
            builder.add(
                bundle_kind="aggregate_metric",
                calls=[call],
                subject=_subject(reference),
                atoms=[
                    builder.atom(
                        semantic_role="metric_value",
                        value=reference.value,
                        display_value=reference.display_value,
                        evidence_ids=[reference.fact_id],
                    ),
                    _period_atom(builder, reference),
                ],
                prohibited=[
                    "Do not calculate a new metric from this value.",
                    "Do not infer causality, profit or future performance.",
                ],
            )
            used_fact_ids.add(reference.fact_id)

        for item in call.request_references:
            requests[item.request_id] = item
            request_sources[item.request_id].append(call)
        for item in call.policy_references:
            policies[item.policy_id] = item
            policy_sources[item.policy_id].append(call)

    for request_id, reference in requests.items():
        builder.add(
            bundle_kind="request_parameter",
            calls=_unique_calls(request_sources[request_id]),
            subject=ClaimBundleSubjectV2_3_2(),
            atoms=[
                builder.atom(
                    semantic_role="request_parameter",
                    value=reference.value,
                    display_value=f"{reference.parameter_name}={reference.value}",
                    evidence_ids=[request_id],
                )
            ],
            prohibited=["Do not infer a user parameter that was not requested."],
        )
    for policy_id, reference in policies.items():
        builder.add(
            bundle_kind="policy_boundary",
            calls=_unique_calls(policy_sources[policy_id]),
            subject=ClaimBundleSubjectV2_3_2(),
            atoms=[
                builder.atom(
                    semantic_role="policy_boundary",
                    value=reference.code,
                    display_value=reference.message,
                    evidence_ids=[policy_id],
                )
            ],
            prohibited=["Do not weaken or reverse the policy boundary."],
        )

    for first_index, first_call in enumerate(envelope.tool_evidence[:-1]):
        peaks = [
            item
            for item in first_call.fact_references
            if item.metric == "peak_period"
            and re.fullmatch(r"\d{4}-\d{2}", item.value)
        ]
        for peak in peaks:
            year, month = map(int, peak.value.split("-"))
            expected_start = f"{peak.value}-01"
            expected_end = f"{peak.value}-{calendar.monthrange(year, month)[1]:02d}"
            for later_call in envelope.tool_evidence[first_index + 1 :]:
                match = next(
                    (
                        item
                        for item in later_call.fact_references
                        if item.period == "custom"
                        and item.start_date == expected_start
                        and item.end_date == expected_end
                    ),
                    None,
                )
                if match is None:
                    continue
                builder.add(
                    bundle_kind="cross_tool_observation",
                    calls=[first_call, later_call],
                    subject=ClaimBundleSubjectV2_3_2(
                        period="custom",
                        start_date=expected_start,
                        end_date=expected_end,
                    ),
                    atoms=[
                        builder.atom(
                            semantic_role="period",
                            value=peak.value,
                            display_value=peak.display_value,
                            evidence_ids=[peak.fact_id, match.fact_id],
                        )
                    ],
                    prohibited=[
                        "Do not claim that the peak period caused entity performance.",
                        "Do not calculate a cross-tool metric.",
                    ],
                )
    return builder.bundles


def build_claim_evidence_envelope(
    envelope: ReportAdmissibleEnvelopeV2_3_1,
) -> ClaimEvidenceEnvelopeV2_3_2:
    return ClaimEvidenceEnvelopeV2_3_2(
        phase="report_terminal_claim_evidence_bundles",
        session_id=envelope.session_id,
        turn_id=envelope.turn_id,
        tool_evidence=envelope.tool_evidence,
        claim_evidence_bundles=build_claim_evidence_bundles(envelope),
        bundle_usage_contract=BundleUsageContractV2_3_2(),
    )


def reference_catalog(
    envelope: ClaimEvidenceEnvelopeV2_3_2,
) -> dict[str, ReportFactReference | ReportRequestReference | ReportPolicyReference]:
    catalog: dict[
        str, ReportFactReference | ReportRequestReference | ReportPolicyReference
    ] = {}
    for call in envelope.tool_evidence:
        catalog.update({item.fact_id: item for item in call.fact_references})
        catalog.update({item.request_id: item for item in call.request_references})
        catalog.update({item.policy_id: item for item in call.policy_references})
    return catalog


__all__ = [
    "BundleUsageContractV2_3_2",
    "ClaimEvidenceBundleV2_3_2",
    "ClaimEvidenceEnvelopeV2_3_2",
    "ClaimSupportAtomV2_3_2",
    "build_claim_evidence_bundles",
    "build_claim_evidence_envelope",
    "reference_catalog",
]
