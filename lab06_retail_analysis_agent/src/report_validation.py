"""Deterministically validate FACT citations before rendering a report."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.evidence_provenance import PolicyRecord, RequestRecord
from src.fact_schema import (
    FactDimension,
    FactMetric,
    FactRecord,
    FactUnit,
)


REPORT_SECTION_ORDER = (
    "用户问题与分析口径",
    "关键经营发现",
    "工具证据与图表",
    "有限解释",
    "经营建议",
    "数据与分析限制",
)
ReportSectionName = Literal[
    "用户问题与分析口径",
    "关键经营发现",
    "工具证据与图表",
    "有限解释",
    "经营建议",
    "数据与分析限制",
]
NUMBER_PATTERN = re.compile(
    r"\d{4}-\d{2}(?:-\d{2}(?:T\d{2}:\d{2}:\d{2})?)?"
    r"|\d[\d,]*(?:\.\d+)?%?"
)


class ReportValidationError(ValueError):
    """Raised when an unvalidated report is rendered."""


class StrictReportModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ReportFactReference(StrictReportModel):
    evidence_type: Literal["FACT"] = "FACT"
    fact_id: str = Field(pattern=r"^FACT-\d{3,}$")
    metric: FactMetric | None = None
    value: str
    display_value: str
    unit: FactUnit
    rank: int | None = Field(ge=1)
    dimensions: list[FactDimension] = Field(default_factory=list)
    period: str
    start_date: str | None
    end_date: str | None


class ReportRequestReference(StrictReportModel):
    evidence_type: Literal["REQUEST"]
    request_id: str = Field(pattern=r"^REQUEST-\d{3,}$")
    parameter_name: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1, max_length=200)
    source: Literal["validated_user_input"]


class ReportPolicyReference(StrictReportModel):
    evidence_type: Literal["POLICY"]
    policy_id: str = Field(pattern=r"^POLICY-\d{3,}$")
    code: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=500)


ReportEvidenceReference = (
    ReportFactReference | ReportRequestReference | ReportPolicyReference
)


class ReportClaim(StrictReportModel):
    statement: str = Field(min_length=1, max_length=1000)
    evidence: list[ReportEvidenceReference] = Field(max_length=40)


class ReportSection(StrictReportModel):
    name: ReportSectionName
    claims: list[ReportClaim] = Field(min_length=1, max_length=12)


class ReportDraft(StrictReportModel):
    schema_version: Literal["1.5.6-h3-report-draft-v1"]
    session_id: str = Field(pattern=r"^SESSION-[A-Za-z0-9_-]+$")
    turn_id: str = Field(pattern=r"^TURN-\d{3,}$")
    title: str = Field(min_length=1, max_length=200)
    sections: list[ReportSection] = Field(min_length=6, max_length=6)

    @model_validator(mode="after")
    def validate_section_order(self) -> ReportDraft:
        names = tuple(section.name for section in self.sections)
        if names != REPORT_SECTION_ORDER:
            raise ValueError("报告必须包含且依次使用六个冻结章节")
        return self


class ReportIssue(StrictReportModel):
    code: str
    location: str
    message: str


class ReportValidationResult(StrictReportModel):
    schema_version: Literal["1.5.6-h3-report-validation-v1"]
    status: Literal["passed", "failed"]
    issues: list[ReportIssue]
    referenced_fact_ids: list[str]
    referenced_request_ids: list[str] = Field(default_factory=list)
    referenced_policy_ids: list[str] = Field(default_factory=list)
    deterministic_checks: list[str]
    manual_review_flags: list[ReportIssue] = Field(default_factory=list)
    manual_review_required_sections: list[str]


def fact_reference(fact: FactRecord) -> ReportFactReference:
    return ReportFactReference(
        fact_id=fact.fact_id,
        metric=fact.metric,
        value=fact.value,
        display_value=fact.display_value,
        unit=fact.unit,
        rank=fact.rank,
        dimensions=fact.dimensions,
        period=fact.analysis_scope.period,
        start_date=fact.analysis_scope.start_date,
        end_date=fact.analysis_scope.end_date,
    )


def request_reference(record: RequestRecord) -> ReportRequestReference:
    return ReportRequestReference(
        evidence_type="REQUEST",
        request_id=record.request_id,
        parameter_name=record.parameter_name,
        value=record.value,
        source=record.source,
    )


def policy_reference(record: PolicyRecord) -> ReportPolicyReference:
    return ReportPolicyReference(
        evidence_type="POLICY",
        policy_id=record.policy_id,
        code=record.code,
        message=record.message,
    )


def _numeric_tokens(text: str) -> set[str]:
    from src.report_evidence_semantic_boundary_v2_2_2 import (
        canonical_numeric_tokens,
    )

    return canonical_numeric_tokens(text)


def _allowed_tokens(facts: list[FactRecord]) -> set[str]:
    from src.report_evidence_semantic_boundary_v2_2_2 import (
        allowed_canonical_tokens,
    )

    return allowed_canonical_tokens(facts)


def validate_report(
    draft: ReportDraft,
    facts: list[FactRecord],
    request_records: list[RequestRecord] | None = None,
    policy_records: list[PolicyRecord] | None = None,
) -> ReportValidationResult:
    from src.report_evidence_semantic_boundary_v2_2_2 import (
        collect_manual_review_flags,
        validate_deterministic_semantics,
    )

    issues: list[ReportIssue] = []
    fact_by_id = {fact.fact_id: fact for fact in facts}
    request_by_id = {
        item.request_id: item for item in (request_records or [])
    }
    policy_by_id = {
        item.policy_id: item for item in (policy_records or [])
    }
    if len(fact_by_id) != len(facts):
        issues.append(
            ReportIssue(
                code="duplicate_fact_id",
                location="facts",
                message="FACT ID不得重复。",
            )
        )

    referenced: list[str] = []
    referenced_requests: list[str] = []
    referenced_policies: list[str] = []
    for section_index, section in enumerate(draft.sections):
        for claim_index, claim in enumerate(section.claims):
            location = f"sections[{section_index}].claims[{claim_index}]"
            if "[FACT-" in claim.statement:
                issues.append(
                    ReportIssue(
                        code="model_supplied_fact_citation",
                        location=location,
                        message="FACT引用必须由程序渲染，陈述中不得自行插入。",
                    )
                )
            claim_facts: list[FactRecord] = []
            seen_in_claim: set[str] = set()
            for reference in claim.evidence:
                if isinstance(reference, ReportRequestReference):
                    reference_id = reference.request_id
                    referenced_requests.append(reference_id)
                    if reference_id in seen_in_claim:
                        issues.append(
                            ReportIssue(
                                code="duplicate_claim_reference",
                                location=location,
                                message=f"重复引用{reference_id}。",
                            )
                        )
                    seen_in_claim.add(reference_id)
                    record = request_by_id.get(reference_id)
                    if record is None:
                        issues.append(
                            ReportIssue(
                                code="unknown_request",
                                location=location,
                                message=f"REQUEST不存在：{reference_id}。",
                            )
                        )
                    elif (
                        record.session_id != draft.session_id
                        or record.turn_id != draft.turn_id
                    ):
                        issues.append(
                            ReportIssue(
                                code="cross_turn_request",
                                location=location,
                                message=f"{reference_id}不属于当前轮次。",
                            )
                        )
                    elif any(
                        observed != expected
                        for observed, expected in (
                            (reference.parameter_name, record.parameter_name),
                            (reference.value, record.value),
                            (reference.source, record.source),
                        )
                    ):
                        issues.append(
                            ReportIssue(
                                code="request_reference_mismatch",
                                location=location,
                                message=f"{reference_id}与REQUEST不一致。",
                            )
                        )
                    continue
                if isinstance(reference, ReportPolicyReference):
                    reference_id = reference.policy_id
                    referenced_policies.append(reference_id)
                    if reference_id in seen_in_claim:
                        issues.append(
                            ReportIssue(
                                code="duplicate_claim_reference",
                                location=location,
                                message=f"重复引用{reference_id}。",
                            )
                        )
                    seen_in_claim.add(reference_id)
                    record = policy_by_id.get(reference_id)
                    if record is None:
                        issues.append(
                            ReportIssue(
                                code="unknown_policy",
                                location=location,
                                message=f"POLICY不存在：{reference_id}。",
                            )
                        )
                    elif any(
                        observed != expected
                        for observed, expected in (
                            (reference.code, record.code),
                            (reference.message, record.message),
                        )
                    ):
                        issues.append(
                            ReportIssue(
                                code="policy_reference_mismatch",
                                location=location,
                                message=f"{reference_id}与POLICY不一致。",
                            )
                        )
                    continue
                referenced.append(reference.fact_id)
                if reference.fact_id in seen_in_claim:
                    issues.append(
                        ReportIssue(
                            code="duplicate_claim_reference",
                            location=location,
                            message=f"重复引用{reference.fact_id}。",
                        )
                    )
                seen_in_claim.add(reference.fact_id)
                fact = fact_by_id.get(reference.fact_id)
                if fact is None:
                    issues.append(
                        ReportIssue(
                            code="unknown_fact",
                            location=location,
                            message=f"FACT不存在：{reference.fact_id}。",
                        )
                    )
                    continue
                claim_facts.append(fact)
                if (
                    fact.session_id != draft.session_id
                    or fact.turn_id != draft.turn_id
                ):
                    issues.append(
                        ReportIssue(
                            code="cross_turn_fact",
                            location=location,
                            message=(
                                f"{reference.fact_id}不属于当前会话轮次。"
                            ),
                        )
                    )
                comparisons = {
                    "value": (reference.value, fact.value),
                    "display_value": (
                        reference.display_value,
                        fact.display_value,
                    ),
                    "unit": (reference.unit, fact.unit),
                    "rank": (reference.rank, fact.rank),
                    "period": (
                        reference.period,
                        fact.analysis_scope.period,
                    ),
                    "start_date": (
                        reference.start_date,
                        fact.analysis_scope.start_date,
                    ),
                    "end_date": (
                        reference.end_date,
                        fact.analysis_scope.end_date,
                    ),
                }
                if reference.metric is not None:
                    comparisons["metric"] = (
                        reference.metric,
                        fact.metric,
                    )
                if reference.dimensions:
                    comparisons["dimensions"] = (
                        reference.dimensions,
                        fact.dimensions,
                    )
                for field, (observed, expected) in comparisons.items():
                    if observed != expected:
                        issues.append(
                            ReportIssue(
                                code=f"fact_{field}_mismatch",
                                location=location,
                                message=(
                                    f"{reference.fact_id}的{field}"
                                    "与FACT不一致。"
                                ),
                            )
                        )

            statement_tokens = _numeric_tokens(claim.statement)
            allowed = _allowed_tokens(claim_facts)
            for reference in claim.evidence:
                if isinstance(reference, ReportRequestReference):
                    allowed.update(_numeric_tokens(reference.value))
                elif isinstance(reference, ReportPolicyReference):
                    allowed.update(_numeric_tokens(reference.message))
            unsupported = statement_tokens - allowed
            for token in sorted(unsupported):
                issues.append(
                    ReportIssue(
                        code="untraceable_numeric_token",
                        location=location,
                        message=f"数值或期间没有FACT证据：{token}。",
                    )
                )

    semantic_issues = validate_deterministic_semantics(draft, facts)
    issues.extend(
        ReportIssue(
            code=issue.code,
            location=issue.location,
            message=(
                f"{issue.message} 触发表达：{issue.token_or_phrase}。"
            ),
        )
        for issue in semantic_issues
    )
    manual_review_flags = [
        ReportIssue(
            code=flag.code,
            location=flag.location,
            message=(
                f"{flag.message} 触发表达：{flag.token_or_phrase}。"
            ),
        )
        for flag in collect_manual_review_flags(draft)
    ]

    return ReportValidationResult(
        schema_version="1.5.6-h3-report-validation-v1",
        status="failed" if issues else "passed",
        issues=issues,
        referenced_fact_ids=list(dict.fromkeys(referenced)),
        referenced_request_ids=list(dict.fromkeys(referenced_requests)),
        referenced_policy_ids=list(dict.fromkeys(referenced_policies)),
        deterministic_checks=[
            "FACT存在且属于当前会话轮次",
            "规范值与展示值一致",
            "单位一致",
            "时间范围一致",
            "排名一致",
            "日期等价规范化后，报告中的数值与期间均可追溯",
            "明确的统计显著性、客单价、商品分类与排名断言有对应FACT能力",
        ],
        manual_review_flags=manual_review_flags,
        manual_review_required_sections=[
            "有限解释",
            "经营建议",
        ],
    )


def render_validated_report(
    draft: ReportDraft,
    facts: list[FactRecord],
    request_records: list[RequestRecord] | None = None,
    policy_records: list[PolicyRecord] | None = None,
) -> str:
    result = validate_report(
        draft,
        facts,
        request_records,
        policy_records,
    )
    if result.status != "passed":
        codes = "、".join(issue.code for issue in result.issues)
        raise ReportValidationError(f"报告校验失败：{codes}")

    lines = [f"# {draft.title}", ""]
    for section in draft.sections:
        lines.extend([f"## {section.name}", ""])
        for claim in section.claims:
            citations = " ".join(
                f"[{getattr(reference, 'fact_id', None) or getattr(reference, 'request_id', None) or getattr(reference, 'policy_id')}]"
                for reference in claim.evidence
            )
            suffix = f" {citations}" if citations else ""
            lines.append(f"- {claim.statement}{suffix}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
