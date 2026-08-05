"""Candidate V2 report boundary: model selects FACT IDs, program injects values."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from src.chart_data import ChartType
from src.fact_schema import (
    AnalysisScope,
    FactDimension,
    FactMetric,
    FactRecord,
    FactUnit,
)
from src.report_validation import REPORT_SECTION_ORDER, ReportSectionName


ClaimKind = Literal[
    "scope",
    "finding",
    "evidence_note",
    "limited_interpretation",
    "recommendation",
    "limitation",
]
SECTION_CLAIM_KIND: dict[ReportSectionName, ClaimKind] = {
    "用户问题与分析口径": "scope",
    "关键经营发现": "finding",
    "工具证据与图表": "evidence_note",
    "有限解释": "limited_interpretation",
    "经营建议": "recommendation",
    "数据与分析限制": "limitation",
}
CHART_SOURCE_TOOLS = {
    "monthly_line": "analyze_time_trend",
    "vertical_bar": "analyze_regions",
    "top_n_horizontal_bar": "rank_products",
    "two_segment_share_bar": "compare_segments",
}
NUMERIC_CHARACTER = re.compile(r"\d")


class ReportFinalizationV2Error(ValueError):
    """Raised when a V2 report plan cannot be deterministically finalized."""


class StrictReportV2Model(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        validate_assignment=True,
    )


def _validate_numeric_free(value: str) -> str:
    if NUMERIC_CHARACTER.search(value):
        raise ValueError("模型叙述和标题不得包含数字")
    if "[FACT-" in value or "CALL-" in value:
        raise ValueError("模型叙述不得包含内部引用编号")
    return value


class ReportClaimPlanV2(StrictReportV2Model):
    claim_kind: ClaimKind
    narrative: str = Field(min_length=1, max_length=800)
    fact_ids: list[str] = Field(max_length=12)

    @field_validator("narrative")
    @classmethod
    def validate_narrative(cls, value: str) -> str:
        return _validate_numeric_free(value)

    @field_validator("fact_ids")
    @classmethod
    def validate_fact_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("同一条陈述不得重复引用FACT")
        if any(
            re.fullmatch(r"FACT-\d{3,}", fact_id) is None
            for fact_id in value
        ):
            raise ValueError("fact_ids格式无效")
        return value

    @model_validator(mode="after")
    def validate_evidence_requirement(self) -> ReportClaimPlanV2:
        if (
            self.claim_kind
            in {
                "finding",
                "evidence_note",
                "limited_interpretation",
                "recommendation",
            }
            and not self.fact_ids
        ):
            raise ValueError(f"{self.claim_kind}必须引用至少一个FACT")
        return self


class ReportSectionPlanV2(StrictReportV2Model):
    name: ReportSectionName
    claims: list[ReportClaimPlanV2] = Field(
        min_length=1,
        max_length=8,
    )

    @model_validator(mode="after")
    def validate_claim_kinds(self) -> ReportSectionPlanV2:
        expected = SECTION_CLAIM_KIND[self.name]
        if any(claim.claim_kind != expected for claim in self.claims):
            raise ValueError(f"{self.name}只允许{expected}陈述")
        return self


class ReportPlanV2(StrictReportV2Model):
    schema_version: Literal["1.5.6-h3-report-plan-v2"]
    session_id: str = Field(pattern=r"^SESSION-[A-Za-z0-9_-]+$")
    turn_id: str = Field(pattern=r"^TURN-\d{3,}$")
    title: str = Field(min_length=1, max_length=200)
    sections: list[ReportSectionPlanV2] = Field(
        min_length=6,
        max_length=6,
    )

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        return _validate_numeric_free(value)

    @model_validator(mode="after")
    def validate_section_order(self) -> ReportPlanV2:
        if tuple(section.name for section in self.sections) != (
            REPORT_SECTION_ORDER
        ):
            raise ValueError("V2报告必须依次包含六个冻结章节")
        return self


class ChartRequestV2(StrictReportV2Model):
    call_id: str = Field(pattern=r"^CALL-\d{3,}$")
    chart_type: ChartType
    title: str = Field(min_length=1, max_length=200)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        return _validate_numeric_free(value)


class FinalReportResponseV2(StrictReportV2Model):
    response_type: Literal["report"]
    report: ReportPlanV2
    chart_requests: list[ChartRequestV2] = Field(max_length=4)


class CanonicalEvidenceV2(StrictReportV2Model):
    fact_id: str
    metric: FactMetric
    value: str
    display_value: str
    unit: FactUnit
    analysis_scope: AnalysisScope
    dimensions: list[FactDimension]
    rank: int | None


class FinalizedClaimV2(StrictReportV2Model):
    claim_kind: ClaimKind
    narrative: str
    evidence: list[CanonicalEvidenceV2]


class FinalizedSectionV2(StrictReportV2Model):
    name: ReportSectionName
    claims: list[FinalizedClaimV2]


class FinalizedReportV2(StrictReportV2Model):
    schema_version: Literal["1.5.6-h3-finalized-report-v2"]
    session_id: str
    turn_id: str
    title: str
    sections: list[FinalizedSectionV2]
    referenced_fact_ids: list[str]


class ReportPlanIssueV2(StrictReportV2Model):
    code: str
    location: str
    message: str


class ReportPlanValidationV2(StrictReportV2Model):
    schema_version: Literal["1.5.6-h3-report-plan-validation-v2"]
    status: Literal["passed", "failed"]
    issues: list[ReportPlanIssueV2]
    referenced_fact_ids: list[str]
    deterministic_checks: list[str]
    manual_review_required_sections: list[str]


def validate_report_plan_v2(
    response: FinalReportResponseV2,
    facts: list[FactRecord],
) -> ReportPlanValidationV2:
    issues: list[ReportPlanIssueV2] = []
    fact_by_id = {fact.fact_id: fact for fact in facts}
    if len(fact_by_id) != len(facts):
        issues.append(
            ReportPlanIssueV2(
                code="duplicate_fact_id",
                location="facts",
                message="FACT ID不得重复",
            )
        )
    referenced: list[str] = []
    report = response.report
    for section_index, section in enumerate(report.sections):
        for claim_index, claim in enumerate(section.claims):
            location = (
                f"sections[{section_index}].claims[{claim_index}]"
            )
            for fact_id in claim.fact_ids:
                referenced.append(fact_id)
                fact = fact_by_id.get(fact_id)
                if fact is None:
                    issues.append(
                        ReportPlanIssueV2(
                            code="unknown_fact",
                            location=location,
                            message=f"FACT不存在：{fact_id}",
                        )
                    )
                    continue
                if (
                    fact.session_id != report.session_id
                    or fact.turn_id != report.turn_id
                ):
                    issues.append(
                        ReportPlanIssueV2(
                            code="cross_turn_fact",
                            location=location,
                            message=f"FACT不属于当前轮：{fact_id}",
                        )
                    )

    fact_call_tools = {
        (fact.call_id, fact.source_tool)
        for fact in facts
    }
    for index, request in enumerate(response.chart_requests):
        expected_tool = CHART_SOURCE_TOOLS[request.chart_type]
        if (request.call_id, expected_tool) not in fact_call_tools:
            issues.append(
                ReportPlanIssueV2(
                    code="invalid_chart_source",
                    location=f"chart_requests[{index}]",
                    message=(
                        f"{request.chart_type}必须引用"
                        f"{expected_tool}对应CALL"
                    ),
                )
            )

    return ReportPlanValidationV2(
        schema_version="1.5.6-h3-report-plan-validation-v2",
        status="failed" if issues else "passed",
        issues=issues,
        referenced_fact_ids=list(dict.fromkeys(referenced)),
        deterministic_checks=[
            "标题和模型叙述不含数字或内部引用编号",
            "章节顺序与claim_kind符合冻结职责",
            "事实发现、解释和建议引用至少一个FACT",
            "FACT存在且属于当前会话轮次",
            "图表请求引用兼容工具对应CALL",
            "数值、单位、期间、维度和排名只由程序注入",
        ],
        manual_review_required_sections=[
            "有限解释",
            "经营建议",
        ],
    )


def _canonical_evidence(fact: FactRecord) -> CanonicalEvidenceV2:
    return CanonicalEvidenceV2(
        fact_id=fact.fact_id,
        metric=fact.metric,
        value=fact.value,
        display_value=fact.display_value,
        unit=fact.unit,
        analysis_scope=fact.analysis_scope,
        dimensions=fact.dimensions,
        rank=fact.rank,
    )


def finalize_report_v2(
    response: FinalReportResponseV2,
    facts: list[FactRecord],
) -> FinalizedReportV2:
    validation = validate_report_plan_v2(response, facts)
    if validation.status != "passed":
        codes = "、".join(issue.code for issue in validation.issues)
        raise ReportFinalizationV2Error(
            f"V2报告计划校验失败：{codes}"
        )
    fact_by_id = {fact.fact_id: fact for fact in facts}
    sections = [
        FinalizedSectionV2(
            name=section.name,
            claims=[
                FinalizedClaimV2(
                    claim_kind=claim.claim_kind,
                    narrative=claim.narrative,
                    evidence=[
                        _canonical_evidence(fact_by_id[fact_id])
                        for fact_id in claim.fact_ids
                    ],
                )
                for claim in section.claims
            ],
        )
        for section in response.report.sections
    ]
    return FinalizedReportV2(
        schema_version="1.5.6-h3-finalized-report-v2",
        session_id=response.report.session_id,
        turn_id=response.report.turn_id,
        title=response.report.title,
        sections=sections,
        referenced_fact_ids=validation.referenced_fact_ids,
    )


def _evidence_text(evidence: CanonicalEvidenceV2) -> str:
    parts = [
        f"[{evidence.fact_id}]",
        f"{evidence.metric}={evidence.display_value}",
        f"unit={evidence.unit}",
        f"period={evidence.analysis_scope.period}",
    ]
    if evidence.analysis_scope.start_date is not None:
        parts.append(f"start={evidence.analysis_scope.start_date}")
    if evidence.analysis_scope.end_date is not None:
        parts.append(f"end={evidence.analysis_scope.end_date}")
    if evidence.dimensions:
        dimensions = ",".join(
            f"{item.name}={item.value}"
            for item in evidence.dimensions
        )
        parts.append(f"dimensions={dimensions}")
    if evidence.rank is not None:
        parts.append(f"rank={evidence.rank}")
    return "；".join(parts)


def render_finalized_report_v2(report: FinalizedReportV2) -> str:
    lines = [f"# {report.title}", ""]
    for section in report.sections:
        lines.extend([f"## {section.name}", ""])
        for claim in section.claims:
            lines.append(f"- {claim.narrative}")
            for evidence in claim.evidence:
                lines.append(f"  - 证据：{_evidence_text(evidence)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
