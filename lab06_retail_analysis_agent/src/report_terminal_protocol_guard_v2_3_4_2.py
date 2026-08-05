"""V2.3.4.2 model-visible protocol isolation and arithmetic-intent guard.

Internal CALL identifiers remain available to deterministic orchestration, FACT
and chart builders.  The model sees only turn-scoped chart source aliases.  A
second deterministic guard rejects attempts to derive a metric from multiple
FACT values before the unchanged formal report validator runs.
"""

from __future__ import annotations

import json
import hashlib
import re
from dataclasses import dataclass
from typing import Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator, model_validator

from src.agent_protocol import (
    BoundaryResponse,
    ChartRequest,
    ClarificationResponse,
    FinalReportResponse,
)
from src.chart_data import CHART_SOURCE_TOOLS, ChartType
from src.report_validation import ReportDraft, ReportEvidenceReference
from src.report_evidence_semantic_boundary_v2_2_2 import canonical_numeric_tokens
from src.section_purpose_contract_v2_3_4_1 import (
    ValidatedPurposeSlotV2_3_4_1,
    ValidatedSectionPurposeEnvelopeV2_3_4_1,
)


INTERNAL_CALL_VALUE_PATTERN = re.compile(r"\bCALL-\d{3,}\b")
CHART_SOURCE_KEY_PATTERN = re.compile(r"\bsource_[a-z0-9]+\b")
MAX_CHART_SOURCES = 4
TOOL_TO_CHART_TYPE: dict[str, ChartType] = {
    tool_name: chart_type
    for chart_type, tool_name in CHART_SOURCE_TOOLS.items()
}

FINAL_INSTRUCTION_V2_3_4_2 = (
    "Write exactly one ordered report section for each validated slot. Every "
    "claim may use only its slot's allowed_evidence and must copy complete local "
    "reference objects. Never borrow evidence across slots or calculate new "
    "values. For charts, choose only a supplied chart_source_key and one of that "
    "source's allowed_chart_types. Do not place evidence IDs or chart source keys "
    "in report prose or titles."
)


class StrictProtocolGuardModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class PublicChartSourceV2_3_4_2(StrictProtocolGuardModel):
    chart_source_key: str = Field(pattern=r"^source_[a-z0-9]+$")
    tool_name: str = Field(min_length=1, max_length=100)
    allowed_chart_types: list[ChartType] = Field(min_length=1, max_length=1)


class InternalChartSourceV2_3_4_2(StrictProtocolGuardModel):
    chart_source_key: str = Field(pattern=r"^source_[a-z0-9]+$")
    internal_call_id: str = Field(pattern=r"^CALL-\d{3,}$")
    tool_name: str = Field(min_length=1, max_length=100)
    allowed_chart_types: list[ChartType] = Field(min_length=1, max_length=1)


class InternalChartSourceRegistryV2_3_4_2(StrictProtocolGuardModel):
    session_id: str = Field(pattern=r"^SESSION-[A-Za-z0-9_-]+$")
    turn_id: str = Field(pattern=r"^TURN-\d{3,}$")
    entries: list[InternalChartSourceV2_3_4_2] = Field(max_length=4)

    @model_validator(mode="after")
    def validate_unique_entries(self) -> "InternalChartSourceRegistryV2_3_4_2":
        aliases = [item.chart_source_key for item in self.entries]
        call_ids = [item.internal_call_id for item in self.entries]
        if len(aliases) != len(set(aliases)):
            raise ValueError("duplicate_chart_source_alias")
        if len(call_ids) != len(set(call_ids)):
            raise ValueError("duplicate_internal_call_mapping")
        return self


class ValidatedModelVisibleEnvelopeV2_3_4_2(StrictProtocolGuardModel):
    phase: Literal[
        "report_terminal_validated_section_purpose_slots_v2_3_4_2"
    ]
    session_id: str = Field(pattern=r"^SESSION-[A-Za-z0-9_-]+$")
    turn_id: str = Field(pattern=r"^TURN-\d{3,}$")
    slots: list[ValidatedPurposeSlotV2_3_4_1] = Field(min_length=6, max_length=6)
    allowed_chart_sources: list[PublicChartSourceV2_3_4_2] = Field(max_length=4)
    instruction: str = Field(min_length=1, max_length=1200)

    @model_validator(mode="after")
    def reject_internal_values(self) -> "ValidatedModelVisibleEnvelopeV2_3_4_2":
        payload = self.model_dump_json()
        if INTERNAL_CALL_VALUE_PATTERN.search(payload):
            raise ValueError("model_visible_internal_call_id")
        return self


class ModelChartRequestV2_3_4_2(StrictProtocolGuardModel):
    chart_source_key: str = Field(pattern=r"^source_[a-z0-9]+$")
    chart_type: ChartType
    title: str = Field(min_length=1, max_length=200)


class ModelFinalReportResponseV2_3_4_2(StrictProtocolGuardModel):
    response_type: Literal["report"]
    report: ReportDraft
    chart_requests: list[ModelChartRequestV2_3_4_2] = Field(max_length=4)

    @field_validator("chart_requests")
    @classmethod
    def reject_duplicate_chart_requests(
        cls, value: list[ModelChartRequestV2_3_4_2]
    ) -> list[ModelChartRequestV2_3_4_2]:
        keys = [
            (item.chart_source_key, item.chart_type, item.title)
            for item in value
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate_chart_source_request")
        return value


ModelAgentControlResponseV2_3_4_2: TypeAlias = (
    ClarificationResponse | BoundaryResponse | ModelFinalReportResponseV2_3_4_2
)
MODEL_CONTROL_ADAPTER_V2_3_4_2 = TypeAdapter(ModelAgentControlResponseV2_3_4_2)


def model_control_response_schema_v2_3_4_2() -> dict[str, Any]:
    """Return the model-facing schema; it intentionally contains no call_id."""
    schema = MODEL_CONTROL_ADAPTER_V2_3_4_2.json_schema()
    serialized = json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
    if "call_id" in serialized or INTERNAL_CALL_VALUE_PATTERN.search(serialized):
        raise ValueError("model_visible_schema_contains_internal_call_id")
    return schema


@dataclass(frozen=True)
class IsolatedTerminalContextV2_3_4_2:
    model_visible: ValidatedModelVisibleEnvelopeV2_3_4_2
    internal_registry: InternalChartSourceRegistryV2_3_4_2


@dataclass(frozen=True)
class ArithmeticIntentIssueV2_3_4_2:
    code: str
    location: str
    intent: str
    phrase: str
    required_metrics: tuple[str, ...]
    observed_metrics: tuple[str, ...]


@dataclass(frozen=True)
class TerminalMappingTraceV2_3_4_2:
    session_id: str
    turn_id: str
    parsed_model_response: dict[str, Any]
    mapped_program_response: dict[str, Any]
    mapped_chart_sources: tuple[tuple[str, str], ...]
    arithmetic_issue_codes: tuple[str, ...]


class ReportTerminalProtocolGuardError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


def _reference_id(reference: ReportEvidenceReference) -> str:
    if reference.evidence_type == "FACT":
        return reference.fact_id
    if reference.evidence_type == "REQUEST":
        return reference.request_id
    return reference.policy_id


def _turn_scoped_source_key(
    *, session_id: str, turn_id: str, source_index: int
) -> str:
    """Derive a non-sensitive alias that cannot be reused by another turn."""
    material = f"{session_id}\x00{turn_id}\x00{source_index}".encode("utf-8")
    digest = hashlib.blake2s(material, digest_size=10).hexdigest()
    return f"source_{digest}"


def build_isolated_terminal_context(
    validated: ValidatedSectionPurposeEnvelopeV2_3_4_1,
) -> IsolatedTerminalContextV2_3_4_2:
    chartable = [
        source
        for source in validated.allowed_chart_sources
        if source.tool_name in TOOL_TO_CHART_TYPE
    ]
    if len(chartable) > MAX_CHART_SOURCES:
        raise ReportTerminalProtocolGuardError(
            "chart_source_capacity_exceeded",
            "the turn contains more chartable calls than the frozen alias pool",
        )
    entries = [
        InternalChartSourceV2_3_4_2(
            chart_source_key=_turn_scoped_source_key(
                session_id=validated.session_id,
                turn_id=validated.turn_id,
                source_index=index,
            ),
            internal_call_id=source.call_id,
            tool_name=source.tool_name,
            allowed_chart_types=[TOOL_TO_CHART_TYPE[source.tool_name]],
        )
        for index, source in enumerate(chartable)
    ]
    registry = InternalChartSourceRegistryV2_3_4_2(
        session_id=validated.session_id,
        turn_id=validated.turn_id,
        entries=entries,
    )
    visible = ValidatedModelVisibleEnvelopeV2_3_4_2(
        phase="report_terminal_validated_section_purpose_slots_v2_3_4_2",
        session_id=validated.session_id,
        turn_id=validated.turn_id,
        slots=validated.slots,
        allowed_chart_sources=[
            PublicChartSourceV2_3_4_2(
                chart_source_key=item.chart_source_key,
                tool_name=item.tool_name,
                allowed_chart_types=item.allowed_chart_types,
            )
            for item in entries
        ],
        instruction=FINAL_INSTRUCTION_V2_3_4_2,
    )
    return IsolatedTerminalContextV2_3_4_2(visible, registry)


def _trusted_metrics_for_claim(
    claim_evidence: list[ReportEvidenceReference],
    slot: ValidatedPurposeSlotV2_3_4_1,
) -> tuple[str, ...]:
    referenced_ids = {_reference_id(item) for item in claim_evidence}
    return tuple(sorted({
        item.metric
        for item in slot.allowed_evidence
        if item.evidence_type == "FACT"
        and item.fact_id in referenced_ids
        and item.metric is not None
    }))


def _trusted_evidence_for_claim(
    claim_evidence: list[ReportEvidenceReference],
    slot: ValidatedPurposeSlotV2_3_4_1,
) -> list[ReportEvidenceReference]:
    referenced_ids = {_reference_id(item) for item in claim_evidence}
    return [
        item
        for item in slot.allowed_evidence
        if _reference_id(item) in referenced_ids
    ]


def _role_aligned_number_issues(
    *,
    statement: str,
    location: str,
    trusted: list[ReportEvidenceReference],
    observed_metrics: tuple[str, ...],
) -> list[ArithmeticIntentIssueV2_3_4_2]:
    role_patterns: tuple[
        tuple[str, re.Pattern[str], tuple[str, ...]], ...
    ] = (
        (
            "items",
            re.compile(r"(?P<number>\d[\d,]*(?:\.\d+)?)\s*件"),
            ("sales_quantity",),
        ),
        (
            "orders",
            re.compile(r"(?P<number>\d[\d,]*(?:\.\d+)?)\s*单"),
            ("order_count",),
        ),
        (
            "currency",
            re.compile(
                r"(?:£\s*(?P<prefix>\d[\d,]*(?:\.\d+)?)|(?P<suffix>\d[\d,]*(?:\.\d+)?)\s*英镑)"
            ),
            ("sales_amount", "average_order_value"),
        ),
        (
            "ratio",
            re.compile(r"(?P<number>\d[\d,]*(?:\.\d+)?)\s*%"),
            (
                "sales_amount_share",
                "sales_row_coverage",
                "sales_amount_coverage",
            ),
        ),
    )
    issues: list[ArithmeticIntentIssueV2_3_4_2] = []
    for role, pattern, required_metrics in role_patterns:
        for match in pattern.finditer(statement):
            number = match.groupdict().get("number")
            if number is None:
                number = match.groupdict().get("prefix") or match.groupdict().get(
                    "suffix"
                )
            assert number is not None
            normalized = number.replace(",", "")
            matched = False
            for item in trusted:
                if item.evidence_type != "FACT" or item.metric not in required_metrics:
                    continue
                candidates = canonical_numeric_tokens(
                    f"{item.value} {item.display_value}"
                )
                normalized_candidates = {
                    candidate.removesuffix("%") for candidate in candidates
                }
                if normalized in normalized_candidates:
                    matched = True
                    break
            if not matched:
                issues.append(
                    ArithmeticIntentIssueV2_3_4_2(
                        code="ambiguous_numeric_role_collision",
                        location=location,
                        intent=f"numeric_role_{role}",
                        phrase=match.group(0),
                        required_metrics=required_metrics,
                        observed_metrics=observed_metrics,
                    )
                )
    return issues


def _unsupported(
    *, location: str, intent: str, phrase: str,
    required: tuple[str, ...], observed: tuple[str, ...],
) -> ArithmeticIntentIssueV2_3_4_2:
    return ArithmeticIntentIssueV2_3_4_2(
        code="derived_metric_fact_missing",
        location=location,
        intent=intent,
        phrase=phrase,
        required_metrics=required,
        observed_metrics=observed,
    )


def validate_model_arithmetic_intent(
    draft: ReportDraft,
    validated: ValidatedSectionPurposeEnvelopeV2_3_4_1,
) -> tuple[ArithmeticIntentIssueV2_3_4_2, ...]:
    """Validate semantic numeric roles, not only numeric token membership."""
    issues: list[ArithmeticIntentIssueV2_3_4_2] = []
    direct_rules: tuple[tuple[str, re.Pattern[str], tuple[str, ...]], ...] = (
        (
            "average_order_value",
            re.compile(r"客单价|平均订单金额|average\s+order\s+value", re.I),
            ("average_order_value",),
        ),
        (
            "sales_amount_share",
            re.compile(r"销售(?:额|金额).{0,6}(?:占比|份额)|sales\s+amount\s+share", re.I),
            ("sales_amount_share",),
        ),
        (
            "sales_row_coverage",
            re.compile(r"销售行.{0,4}覆盖率|sales\s+row\s+coverage", re.I),
            ("sales_row_coverage",),
        ),
        (
            "sales_amount_coverage",
            re.compile(r"销售额.{0,4}覆盖率|sales\s+amount\s+coverage", re.I),
            ("sales_amount_coverage",),
        ),
    )
    unsupported_rules: tuple[tuple[str, re.Pattern[str]], ...] = (
        (
            "items_per_order",
            re.compile(
                r"每(?:笔|单).{0,6}(?:平均)?(?:销量|件数)|单均(?:销量|件数)|件\s*/\s*单|items?\s+per\s+order",
                re.I,
            ),
        ),
        (
            "growth_rate",
            re.compile(r"同比|环比|增长率|增幅|变化率|growth\s+rate", re.I),
        ),
        (
            "unsupported_average",
            re.compile(r"月均|日均|周均|平均(?:销量|销售额|订单数|客户数|件数)", re.I),
        ),
        (
            "difference",
            re.compile(
                r"差额|相差\s*\d|多出\s*\d|少了\s*\d|高出\s*\d|低于\s*\d|(?:高|低|多|少)\s*\d",
                re.I,
            ),
        ),
        (
            "multiple",
            re.compile(r"\d[\d,.]*\s*倍|倍数|几倍|times\s+as", re.I),
        ),
        (
            "computed_equality",
            re.compile(r"(?:销量|订单数|销售额).{0,12}(?:相同|相等)|(?:相同|相等).{0,12}(?:销量|订单数|销售额)"),
        ),
        (
            "explicit_arithmetic_expression",
            re.compile(
                r"\d[\d,.]*\s*(?:\+|×|\*|÷|/)\s*\d[\d,.]*"
                r"|\d[\d,.]*\s+-\s+\d[\d,.]*"
                r"|\d[\d,.]*-\d[\d,.]*\s*="
                r"|相除|除以|相加|相减|求和",
                re.I,
            ),
        ),
    )
    for section_index, (section, slot) in enumerate(
        zip(draft.sections, validated.slots, strict=True)
    ):
        for claim_index, claim in enumerate(section.claims):
            location = f"sections[{section_index}].claims[{claim_index}]"
            metrics = _trusted_metrics_for_claim(claim.evidence, slot)
            trusted = _trusted_evidence_for_claim(claim.evidence, slot)
            metric_set = set(metrics)
            issue_count_before_claim = len(issues)
            for intent, pattern in unsupported_rules:
                match = pattern.search(claim.statement)
                if match is not None:
                    issues.append(
                        ArithmeticIntentIssueV2_3_4_2(
                            code="unsupported_derived_metric_intent",
                            location=location,
                            intent=intent,
                            phrase=match.group(0),
                            required_metrics=(),
                            observed_metrics=metrics,
                        )
                    )
                    break
            else:
                for intent, pattern, required in direct_rules:
                    match = pattern.search(claim.statement)
                    if match is not None and not metric_set.intersection(required):
                        issues.append(
                            _unsupported(
                                location=location,
                                intent=intent,
                                phrase=match.group(0),
                                required=required,
                                observed=metrics,
                            )
                        )
                        break
                else:
                    generic_share = re.search(
                        r"占比|份额|比例|\bshare\b", claim.statement, re.I
                    )
                    generic_share_metrics = (
                        "sales_amount_share",
                        "sales_row_coverage",
                        "sales_amount_coverage",
                    )
                    if generic_share is not None and not metric_set.intersection(
                        generic_share_metrics
                    ):
                        issues.append(
                            _unsupported(
                                location=location,
                                intent="generic_share_or_ratio",
                                phrase=generic_share.group(0),
                                required=generic_share_metrics,
                                observed=metrics,
                            )
                        )
                        continue
                    if re.search(r"合计|总和|sum\s+of", claim.statement, re.I):
                        same_metric_counts: dict[str, int] = {}
                        referenced_ids = {_reference_id(item) for item in claim.evidence}
                        for item in slot.allowed_evidence:
                            if (
                                item.evidence_type == "FACT"
                                and item.fact_id in referenced_ids
                                and item.metric is not None
                                and item.dimensions
                            ):
                                same_metric_counts[item.metric] = (
                                    same_metric_counts.get(item.metric, 0) + 1
                                )
                        if any(count > 1 for count in same_metric_counts.values()):
                            issues.append(
                                ArithmeticIntentIssueV2_3_4_2(
                                    code="unsupported_derived_metric_intent",
                                    location=location,
                                    intent="multi_fact_sum",
                                    phrase="合计/总和",
                                    required_metrics=(),
                                    observed_metrics=metrics,
                                )
                            )
            if len(issues) == issue_count_before_claim:
                issues.extend(
                    _role_aligned_number_issues(
                        statement=claim.statement,
                        location=location,
                        trusted=trusted,
                        observed_metrics=metrics,
                    )
                )
    return tuple(issues)


def _assert_no_internal_identifier_in_model_response(content: str) -> None:
    if INTERNAL_CALL_VALUE_PATTERN.search(content):
        raise ReportTerminalProtocolGuardError(
            "model_visible_internal_call_id",
            "the model response contains an internal CALL value",
        )
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ReportTerminalProtocolGuardError(
            "invalid_terminal_json", "the model response is not valid JSON"
        ) from exc

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            if "call_id" in value or "internal_call_id" in value:
                raise ReportTerminalProtocolGuardError(
                    "model_visible_internal_call_id",
                    "the model response contains an internal identifier field",
                )
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(payload)


def map_model_report_to_internal_response(
    *,
    content: str,
    context: IsolatedTerminalContextV2_3_4_2,
    trusted_validated: ValidatedSectionPurposeEnvelopeV2_3_4_1,
) -> tuple[FinalReportResponse, TerminalMappingTraceV2_3_4_2]:
    """Parse a model-safe response and restore internal CALLs deterministically."""
    _assert_no_internal_identifier_in_model_response(content)
    try:
        parsed = ModelFinalReportResponseV2_3_4_2.model_validate_json(content)
    except ValueError as exc:
        raise ReportTerminalProtocolGuardError(
            "model_terminal_schema_invalid",
            "the terminal response does not match the model-visible schema",
        ) from exc
    registry = context.internal_registry
    if (parsed.report.session_id, parsed.report.turn_id) != (
        registry.session_id,
        registry.turn_id,
    ):
        raise ReportTerminalProtocolGuardError(
            "cross_turn_chart_source_alias",
            "the report session or turn differs from the alias registry",
        )
    by_alias = {item.chart_source_key: item for item in registry.entries}
    chart_requests: list[ChartRequest] = []
    mapped_pairs: list[tuple[str, str]] = []
    for request in parsed.chart_requests:
        entry = by_alias.get(request.chart_source_key)
        if entry is None:
            raise ReportTerminalProtocolGuardError(
                "unknown_chart_source_alias",
                f"unknown chart source alias: {request.chart_source_key}",
            )
        if request.chart_type not in entry.allowed_chart_types:
            raise ReportTerminalProtocolGuardError(
                "chart_source_alias_tool_mismatch",
                f"{request.chart_type} is not allowed for {request.chart_source_key}",
            )
        chart_requests.append(
            ChartRequest(
                call_id=entry.internal_call_id,
                chart_type=request.chart_type,
                title=request.title,
            )
        )
        mapped_pairs.append((request.chart_source_key, entry.internal_call_id))
    for statement in (
        [parsed.report.title]
        + [
            claim.statement
            for section in parsed.report.sections
            for claim in section.claims
        ]
        + [request.title for request in parsed.chart_requests]
    ):
        if CHART_SOURCE_KEY_PATTERN.search(statement):
            raise ReportTerminalProtocolGuardError(
                "chart_source_alias_in_report_prose",
                "chart source aliases are allowed only in chart_requests",
            )
    mapped = FinalReportResponse(
        response_type="report",
        report=parsed.report,
        chart_requests=chart_requests,
    )
    trace = TerminalMappingTraceV2_3_4_2(
        session_id=registry.session_id,
        turn_id=registry.turn_id,
        parsed_model_response=parsed.model_dump(mode="json"),
        mapped_program_response=mapped.model_dump(mode="json"),
        mapped_chart_sources=tuple(mapped_pairs),
        arithmetic_issue_codes=(),
    )
    return mapped, trace


__all__ = [
    "ArithmeticIntentIssueV2_3_4_2",
    "InternalChartSourceRegistryV2_3_4_2",
    "IsolatedTerminalContextV2_3_4_2",
    "ModelFinalReportResponseV2_3_4_2",
    "ReportTerminalProtocolGuardError",
    "TerminalMappingTraceV2_3_4_2",
    "ValidatedModelVisibleEnvelopeV2_3_4_2",
    "build_isolated_terminal_context",
    "map_model_report_to_internal_response",
    "model_control_response_schema_v2_3_4_2",
    "validate_model_arithmetic_intent",
]
