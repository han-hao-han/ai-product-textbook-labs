"""V3 claim-level terminal controller.

The model writes prose for a deterministic list of claims.  The program owns
claim identity, section placement, evidence binding, chart sources, and final
assembly into the frozen report schema.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.agent_protocol import ChartRequest, FinalReportResponse
from src.fact_schema import AnalysisScope, FactRecord
from src.report_terminal_protocol_guard_v2_3_4_2 import (
    IsolatedTerminalContextV2_3_4_2,
    validate_model_arithmetic_intent,
)
from src.report_evidence_semantic_boundary_v2_2_2 import (
    canonical_numeric_tokens,
    validate_deterministic_semantics,
)
from src.report_validation import (
    REPORT_SECTION_ORDER,
    ReportClaim,
    ReportDraft,
    ReportEvidenceReference,
    ReportSection,
)
from src.section_purpose_contract_v2_3_4_1 import (
    ValidatedSectionPurposeEnvelopeV2_3_4_1,
)
from src.terminal_claim_groups_v10 import required_claim_fact_groups_v10
from src.terminal_report_feedback_v13 import terminal_report_issues_v13


CLAIM_PLAN_PHASE = "report_terminal_claim_plan_v3"
CLAIM_RESPONSE_PHASE = "claim_statement_response_v3"
FORBIDDEN_PROSE_IDENTIFIER = re.compile(
    r"\b(?:FACT|CLAIM|SLOT|ATOM|CALL)-\d+\b|\bsource_[0-9a-f]+\b",
    re.IGNORECASE,
)
NUMERIC_TOKEN = re.compile(
    r"\d{4}-\d{2}(?:-\d{2})?|\d[\d,]*(?:\.\d+)?%?"
)
EMPTY_EVIDENCE_METRIC_TERM = re.compile(
    r"客单价|平均订单金额|销售额|销量|销售数量|订单数|客户数|占比|份额|增长率|增长幅度",
    re.IGNORECASE,
)


class StrictClaimControllerModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ModelVisibleClaimPlanV3(StrictClaimControllerModel):
    claim_id: str = Field(pattern=r"^CLAIM-\d{3,}$")
    slot_id: str = Field(pattern=r"^SLOT-00[1-6]$")
    section_name: str
    purpose: str = Field(min_length=1, max_length=500)
    required_literals: list[str] = Field(max_length=40)


class ModelVisibleChartPlanV3(StrictClaimControllerModel):
    chart_plan_id: str = Field(pattern=r"^CHART-\d{3,}$")
    tool_name: str = Field(min_length=1, max_length=100)
    chart_type: str = Field(min_length=1, max_length=100)


class ClaimPlanEnvelopeV3(StrictClaimControllerModel):
    phase: Literal["report_terminal_claim_plan_v3"]
    session_id: str = Field(pattern=r"^SESSION-[A-Za-z0-9_-]+$")
    turn_id: str = Field(pattern=r"^TURN-\d{3,}$")
    claims: list[ModelVisibleClaimPlanV3] = Field(min_length=6, max_length=72)
    chart_plans: list[ModelVisibleChartPlanV3] = Field(max_length=4)
    instruction: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_order(self) -> "ClaimPlanEnvelopeV3":
        expected_claims = [f"CLAIM-{i:03d}" for i in range(1, len(self.claims) + 1)]
        if [item.claim_id for item in self.claims] != expected_claims:
            raise ValueError("claim plan IDs must be contiguous and ordered")
        expected_charts = [f"CHART-{i:03d}" for i in range(1, len(self.chart_plans) + 1)]
        if [item.chart_plan_id for item in self.chart_plans] != expected_charts:
            raise ValueError("chart plan IDs must be contiguous and ordered")
        return self


class ClaimStatementV3(StrictClaimControllerModel):
    claim_id: str = Field(pattern=r"^CLAIM-\d{3,}$")
    statement: str = Field(min_length=1, max_length=1000)


class ChartTitleV3(StrictClaimControllerModel):
    chart_plan_id: str = Field(pattern=r"^CHART-\d{3,}$")
    title: str = Field(min_length=1, max_length=200)


class ClaimStatementResponseV3(StrictClaimControllerModel):
    phase: Literal["claim_statement_response_v3"]
    session_id: str = Field(pattern=r"^SESSION-[A-Za-z0-9_-]+$")
    turn_id: str = Field(pattern=r"^TURN-\d{3,}$")
    title: str = Field(min_length=1, max_length=200)
    claims: list[ClaimStatementV3] = Field(min_length=6, max_length=72)
    chart_titles: list[ChartTitleV3] = Field(max_length=4)


@dataclass(frozen=True)
class InternalClaimPlanV3:
    claim_id: str
    slot_id: str
    section_name: str
    purpose: str
    evidence: tuple[ReportEvidenceReference, ...]
    required_literals: tuple[str, ...]


@dataclass(frozen=True)
class InternalChartPlanV3:
    chart_plan_id: str
    call_id: str
    tool_name: str
    chart_type: str


@dataclass(frozen=True)
class ClaimControllerContextV3:
    model_visible: ClaimPlanEnvelopeV3
    claims: tuple[InternalClaimPlanV3, ...]
    charts: tuple[InternalChartPlanV3, ...]


class ClaimControllerValidationError(ValueError):
    def __init__(self, code: str, message: str, *, issues: list[dict] | None = None) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.issues = issues or [{"code": code, "message": message}]


def _reference_value(reference: ReportEvidenceReference) -> str:
    if reference.evidence_type == "FACT":
        return reference.value
    if reference.evidence_type == "REQUEST":
        return reference.value
    return reference.message


def _required_literals(references: list[ReportEvidenceReference]) -> tuple[str, ...]:
    values: list[str] = []
    for reference in references:
        values.append(_reference_value(reference))
        if reference.evidence_type == "FACT":
            values.extend(item.value for item in reference.dimensions)
    return tuple(dict.fromkeys(item for item in values if item))


def build_claim_controller_context_v3(
    validated: ValidatedSectionPurposeEnvelopeV2_3_4_1,
    isolated: IsolatedTerminalContextV2_3_4_2,
) -> ClaimControllerContextV3:
    """Convert selected atoms into claim-local immutable evidence plans."""
    internal_claims: list[InternalClaimPlanV3] = []

    def add(
        slot_index: int,
        evidence: list[ReportEvidenceReference],
        purpose: str,
        *,
        required_literals: tuple[str, ...] | None = None,
    ) -> None:
        slot = validated.slots[slot_index]
        internal_claims.append(
            InternalClaimPlanV3(
                claim_id=f"CLAIM-{len(internal_claims) + 1:03d}",
                slot_id=slot.slot_id,
                section_name=slot.section_name,
                purpose=purpose,
                evidence=tuple(evidence),
                required_literals=(
                    _required_literals(evidence)
                    if required_literals is None
                    else required_literals
                ),
            )
        )

    # Scope: one independently traceable request/fixed-scope claim per reference.
    scope_groups: dict[str, list[ReportEvidenceReference]] = {}
    for reference in validated.slots[0].allowed_evidence:
        scope_groups.setdefault(_reference_value(reference), []).append(reference)
    for value, references in scope_groups.items():
        labels = [
            reference.parameter_name
            if reference.evidence_type == "REQUEST"
            else (reference.metric or "selection_scope")
            for reference in references
        ]
        add(
            0,
            references,
            "Restate only the validated scope field "
            + "/".join(dict.fromkeys(labels))
            + f" using {value}; include no other scope fields or results.",
        )
    if not validated.slots[0].allowed_evidence:
        add(0, [], "State that no additional validated scope value is available; use no numbers.")

    # Results: deterministic grouping prevents one large claim from dropping a FACT.
    result_evidence = validated.slots[1].allowed_evidence
    fact_by_id = {
        item.fact_id: item for item in result_evidence if item.evidence_type == "FACT"
    }
    groups = required_claim_fact_groups_v10(result_evidence)
    for group in groups:
        evidence = [fact_by_id[fact_id] for fact_id in group]
        add(1, evidence, "State exactly this deterministic result group and every required literal.")

    # Method, interpretation and recommendation are deliberately bounded to one claim.
    representative = validated.slots[2].allowed_evidence[:1]
    add(
        2,
        representative,
        "Describe only deterministic tool and shared-FACT provenance; do not add metrics or numbers.",
        required_literals=(),
    )
    add(3, [], "Give one cautious descriptive interpretation without numbers, causes or forecasts.")
    add(4, [], "Give one human-review action without numbers, guarantees or automatic decisions.")

    policies = validated.slots[5].allowed_evidence
    if policies:
        for reference in policies:
            add(5, [reference], "State this policy or data limitation exactly.")
    else:
        add(5, [], "State that conclusions are limited to the available historical data; use no numbers.")

    counts = {
        slot.slot_id: sum(item.slot_id == slot.slot_id for item in internal_claims)
        for slot in validated.slots
    }
    if any(count < 1 or count > 12 for count in counts.values()):
        raise ClaimControllerValidationError(
            "claim_plan_section_capacity", "each frozen section requires one to twelve claims"
        )

    internal_charts = tuple(
        InternalChartPlanV3(
            chart_plan_id=f"CHART-{index:03d}",
            call_id=entry.internal_call_id,
            tool_name=entry.tool_name,
            chart_type=entry.allowed_chart_types[0],
        )
        for index, entry in enumerate(isolated.internal_registry.entries, start=1)
    )
    visible_claims = [
        ModelVisibleClaimPlanV3(
            claim_id=item.claim_id,
            slot_id=item.slot_id,
            section_name=item.section_name,
            purpose=item.purpose,
            required_literals=list(item.required_literals),
        )
        for item in internal_claims
    ]
    visible_charts = [
        ModelVisibleChartPlanV3(
            chart_plan_id=item.chart_plan_id,
            tool_name=item.tool_name,
            chart_type=item.chart_type,
        )
        for item in internal_charts
    ]
    envelope = ClaimPlanEnvelopeV3(
        phase=CLAIM_PLAN_PHASE,
        session_id=validated.session_id,
        turn_id=validated.turn_id,
        claims=visible_claims,
        chart_plans=visible_charts,
        instruction=(
            "Return one statement for every claim_id and one title for every chart_plan_id, "
            "in the supplied order. Copy every required_literals item exactly into that claim. "
            "Do not output evidence, tools, IDs in prose, calculations, or additional claims."
        ),
    )
    serialized = envelope.model_dump_json()
    if re.search(r"\bCALL-\d+\b|\bsource_[0-9a-f]+\b", serialized, re.I):
        raise ClaimControllerValidationError(
            "internal_identifier_visible", "model-visible claim plan contains an internal identifier"
        )
    return ClaimControllerContextV3(envelope, tuple(internal_claims), internal_charts)


def _validate_model_prose(
    response: ClaimStatementResponseV3,
    context: ClaimControllerContextV3,
) -> list[dict]:
    issues: list[dict] = []
    if (response.session_id, response.turn_id) != (
        context.model_visible.session_id,
        context.model_visible.turn_id,
    ):
        issues.append({"code": "cross_turn_claim_response", "location": "response"})
    expected_claim_ids = [item.claim_id for item in context.claims]
    if [item.claim_id for item in response.claims] != expected_claim_ids:
        issues.append({"code": "claim_id_order_mismatch", "location": "claims"})
    expected_chart_ids = [item.chart_plan_id for item in context.charts]
    if [item.chart_plan_id for item in response.chart_titles] != expected_chart_ids:
        issues.append({"code": "chart_plan_id_order_mismatch", "location": "chart_titles"})
    prose = [response.title, *(item.statement for item in response.claims), *(item.title for item in response.chart_titles)]
    for index, value in enumerate(prose):
        if FORBIDDEN_PROSE_IDENTIFIER.search(value):
            issues.append({"code": "internal_or_plan_identifier_in_prose", "location": f"prose[{index}]"})
    if NUMERIC_TOKEN.search(response.title):
        issues.append({"code": "numeric_title", "location": "title"})
    for index, (statement, plan) in enumerate(zip(response.claims, context.claims)):
        compact_statement = "".join(statement.statement.split())
        missing = [
            literal
            for literal in plan.required_literals
            if literal not in statement.statement
            and "".join(literal.split()) not in compact_statement
        ]
        if missing:
            issues.append({
                "code": "required_literal_missing",
                "location": f"claims[{index}]",
                "missing_literals": missing,
            })
        if not plan.evidence and NUMERIC_TOKEN.search(statement.statement):
            issues.append({"code": "numeric_empty_evidence_claim", "location": f"claims[{index}]"})
        if not plan.evidence:
            metric_match = EMPTY_EVIDENCE_METRIC_TERM.search(statement.statement)
            if metric_match is not None:
                issues.append(
                    {
                        "code": "claim_local_metric_without_evidence",
                        "location": f"claims[{index}]",
                        "trigger_phrase": metric_match.group(0),
                        "instruction": (
                            "remove this metric-specific interpretation; write only a generic "
                            "human-review interpretation or action without metric terms"
                        ),
                    }
                )
        allowed_tokens: set[str] = set()
        for reference in plan.evidence:
            if reference.evidence_type == "FACT":
                candidates = [
                    reference.value,
                    reference.display_value,
                    reference.start_date or "",
                    reference.end_date or "",
                    *(item.value for item in reference.dimensions),
                ]
            elif reference.evidence_type == "REQUEST":
                candidates = [reference.value]
            else:
                candidates = [reference.message]
            for candidate in candidates:
                allowed_tokens.update(canonical_numeric_tokens(candidate))
        unsupported = canonical_numeric_tokens(statement.statement) - allowed_tokens
        for token in sorted(unsupported):
            issues.append(
                {
                    "code": "claim_local_numeric_token",
                    "location": f"claims[{index}]",
                    "unsupported_literal": token,
                    "instruction": "remove this number because it belongs to another claim",
                }
            )
    for index, item in enumerate(response.chart_titles):
        if NUMERIC_TOKEN.search(item.title):
            issues.append({"code": "numeric_chart_title", "location": f"chart_titles[{index}]"})
    fatal_codes = {
        "cross_turn_claim_response",
        "claim_id_order_mismatch",
        "chart_plan_id_order_mismatch",
    }
    if any(item["code"] in fatal_codes for item in issues):
        raise ClaimControllerValidationError(
            "claim_statement_validation_failed", "model claim statements violate the deterministic plan", issues=issues
        )
    return issues


def assemble_final_report_v3(
    response: ClaimStatementResponseV3,
    context: ClaimControllerContextV3,
    validated: ValidatedSectionPurposeEnvelopeV2_3_4_1,
) -> FinalReportResponse:
    """Attach trusted evidence and chart call IDs, then enforce frozen guards."""
    issues = _validate_model_prose(response, context)
    statements = {item.claim_id: item.statement for item in response.claims}
    sections: list[ReportSection] = []
    for slot in validated.slots:
        claims = [
            ReportClaim(statement=statements[item.claim_id], evidence=list(item.evidence))
            for item in context.claims
            if item.slot_id == slot.slot_id
        ]
        sections.append(ReportSection(name=slot.section_name, claims=claims))
    title_by_id = {item.chart_plan_id: item.title for item in response.chart_titles}
    result = FinalReportResponse(
        response_type="report",
        report=ReportDraft(
            schema_version="1.5.6-h3-report-draft-v1",
            session_id=response.session_id,
            turn_id=response.turn_id,
            title=response.title,
            sections=sections,
        ),
        chart_requests=[
            ChartRequest(call_id=item.call_id, chart_type=item.chart_type, title=title_by_id[item.chart_plan_id])
            for item in context.charts
        ],
    )
    from src.online_native_tool_candidate_v2_3_4 import validate_report_slot_binding

    validate_report_slot_binding(result, validated)
    arithmetic = validate_model_arithmetic_intent(result.report, validated)
    issues.extend([
        {
            "code": item.code,
            "location": item.location,
            "intent": item.intent,
            "trigger_phrase": item.phrase,
            "instruction": (
                "remove this metric or arithmetic phrase from this claim; "
                "the claim may use only its own required_literals and purpose"
            ),
        }
        for item in arithmetic
    ])
    synthetic_facts: list[FactRecord] = []
    seen_fact_ids: set[str] = set()
    for section in result.report.sections:
        for claim in section.claims:
            for reference in claim.evidence:
                if reference.evidence_type != "FACT" or reference.fact_id in seen_fact_ids:
                    continue
                seen_fact_ids.add(reference.fact_id)
                synthetic_facts.append(
                    FactRecord(
                        schema_version="1.5.6-h3-fact-v1",
                        fact_id=reference.fact_id,
                        session_id=result.report.session_id,
                        turn_id=result.report.turn_id,
                        call_id="CALL-999",
                        fact_type="ranked_metric" if reference.rank is not None else "metric",
                        metric=reference.metric,
                        value=reference.value,
                        display_value=reference.display_value,
                        unit=reference.unit,
                        analysis_scope=AnalysisScope(
                            fact_layer="v3_semantic_preflight",
                            period=reference.period,
                            start_date=reference.start_date,
                            end_date=reference.end_date,
                            row_count=0,
                        ),
                        dimensions=reference.dimensions,
                        rank=reference.rank,
                        source_tool="v3_semantic_preflight",
                        source_result_path="results/v3_semantic_preflight.json",
                    )
                )
    issues.extend(
        {
            "code": item.code,
            "location": item.location,
            "trigger_phrase": item.token_or_phrase,
            "instruction": (
                "remove or localize this phrase because the current claim lacks "
                "the FACT metric/rank required by the frozen semantic validator"
            ),
        }
        for item in validate_deterministic_semantics(result.report, synthetic_facts)
    )
    issues.extend(terminal_report_issues_v13(result))
    deduplicated: list[dict] = []
    seen_issue_keys: set[tuple[str, str]] = set()
    for item in issues:
        key = (str(item.get("code")), str(item.get("location")))
        if key not in seen_issue_keys:
            seen_issue_keys.add(key)
            deduplicated.append(item)
    issues = deduplicated
    if issues:
        raise ClaimControllerValidationError(
            "deterministic_report_validation_failed",
            "assembled report contains unsupported local semantics or numeric tokens",
            issues=issues,
        )
    return result


__all__ = [
    "CLAIM_PLAN_PHASE", "CLAIM_RESPONSE_PHASE", "ClaimControllerContextV3",
    "ClaimControllerValidationError", "ClaimPlanEnvelopeV3",
    "ClaimStatementResponseV3", "assemble_final_report_v3",
    "build_claim_controller_context_v3",
]
