"""Controlled report templates with deterministic FACT signature checks."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.analysis_recipes_v2_1 import RecipeId
from src.fact_schema import FactRecord
from src.report_validation import REPORT_SECTION_ORDER, ReportSectionName


TemplateId = Literal[
    "scope_from_facts",
    "profile_summary",
    "metric_summary",
    "peak_period_finding",
    "ranked_entities_finding",
    "segment_comparison_finding",
    "customer_coverage_finding",
    "tool_evidence_summary",
    "descriptive_only",
    "verify_with_additional_data",
    "data_limitations",
]
ALLOWED_TEMPLATES_BY_SECTION: dict[
    ReportSectionName,
    set[TemplateId],
] = {
    "用户问题与分析口径": {"scope_from_facts"},
    "关键经营发现": {
        "profile_summary",
        "metric_summary",
        "peak_period_finding",
        "ranked_entities_finding",
        "segment_comparison_finding",
        "customer_coverage_finding",
    },
    "工具证据与图表": {"tool_evidence_summary"},
    "有限解释": {"descriptive_only"},
    "经营建议": {"verify_with_additional_data"},
    "数据与分析限制": {"data_limitations"},
}


class StrictSemanticModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        validate_assignment=True,
    )


class SemanticBlockPlanV2_1(StrictSemanticModel):
    template_id: TemplateId
    fact_ids: list[str] = Field(max_length=24)

    @model_validator(mode="after")
    def validate_fact_id_shape(self) -> SemanticBlockPlanV2_1:
        if len(self.fact_ids) != len(set(self.fact_ids)):
            raise ValueError("同一模板块不得重复FACT")
        if any(
            re.fullmatch(r"FACT-\d{3,}", fact_id) is None
            for fact_id in self.fact_ids
        ):
            raise ValueError("fact_ids格式无效")
        return self


class SemanticSectionPlanV2_1(StrictSemanticModel):
    name: ReportSectionName
    blocks: list[SemanticBlockPlanV2_1] = Field(
        min_length=1,
        max_length=8,
    )

    @model_validator(mode="after")
    def validate_template_scope(self) -> SemanticSectionPlanV2_1:
        allowed = ALLOWED_TEMPLATES_BY_SECTION[self.name]
        if any(
            block.template_id not in allowed for block in self.blocks
        ):
            raise ValueError(f"{self.name}包含职责外模板")
        return self


class SemanticReportPlanV2_1(StrictSemanticModel):
    schema_version: Literal["1.5.6-h3-semantic-report-plan-v2.1"]
    session_id: str = Field(pattern=r"^SESSION-[A-Za-z0-9_-]+$")
    turn_id: str = Field(pattern=r"^TURN-\d{3,}$")
    recipe_id: RecipeId
    sections: list[SemanticSectionPlanV2_1] = Field(
        min_length=6,
        max_length=6,
    )

    @model_validator(mode="after")
    def validate_section_order(self) -> SemanticReportPlanV2_1:
        if tuple(section.name for section in self.sections) != (
            REPORT_SECTION_ORDER
        ):
            raise ValueError("语义报告必须依次包含六个冻结章节")
        return self


class SemanticIssueV2_1(StrictSemanticModel):
    code: str
    location: str
    message: str


class SemanticValidationV2_1(StrictSemanticModel):
    schema_version: Literal[
        "1.5.6-h3-semantic-report-validation-v2.1"
    ]
    status: Literal["passed", "failed"]
    issues: list[SemanticIssueV2_1]
    referenced_fact_ids: list[str]
    deterministic_checks: list[str]


FACT_REQUIRED_TEMPLATES = {
    "scope_from_facts",
    "profile_summary",
    "metric_summary",
    "peak_period_finding",
    "ranked_entities_finding",
    "segment_comparison_finding",
    "customer_coverage_finding",
    "tool_evidence_summary",
    "descriptive_only",
}


def _dimension_value(
    fact: FactRecord,
    name: str,
) -> str | None:
    return next(
        (
            dimension.value
            for dimension in fact.dimensions
            if dimension.name == name
        ),
        None,
    )


def _signature_error(
    template_id: TemplateId,
    facts: list[FactRecord],
) -> str | None:
    if template_id in FACT_REQUIRED_TEMPLATES and not facts:
        return "该模板必须引用至少一个当前轮FACT"
    if (
        template_id
        in {"verify_with_additional_data", "data_limitations"}
        and facts
    ):
        return "固定建议与限制模板不得附加FACT以暗示额外结论"
    if template_id == "profile_summary" and any(
        fact.source_tool != "get_data_profile" for fact in facts
    ):
        return "数据概况模板只能引用get_data_profile FACT"
    if template_id == "peak_period_finding":
        peaks = [
            fact
            for fact in facts
            if (
                fact.source_tool == "analyze_time_trend"
                and fact.metric == "peak_period"
            )
        ]
        if len(peaks) != 1:
            return "峰值模板要求唯一analyze_time_trend peak_period FACT"
        peak_month = peaks[0].value
        supporting_metrics = [
            fact
            for fact in facts
            if (
                fact.source_tool == "analyze_time_trend"
                and fact.metric
                in {
                    "sales_amount",
                    "sales_quantity",
                    "order_count",
                    "average_order_value",
                }
                and fact.rank == 1
                and _dimension_value(fact, "month") == peak_month
            )
        ]
        if not supporting_metrics:
            return "峰值模板缺少同月且rank为一的指标FACT"
    if template_id == "ranked_entities_finding":
        ranked = [
            fact for fact in facts if fact.fact_type == "ranked_metric"
        ]
        if len(ranked) != len(facts):
            return "排名模板只能引用ranked_metric FACT"
        if any(fact.rank is None for fact in ranked):
            return "排名模板FACT必须包含rank"
        tools = {fact.source_tool for fact in ranked}
        metrics = {fact.metric for fact in ranked}
        ranks = sorted(
            {fact.rank for fact in ranked if fact.rank is not None}
        )
        if (
            len(tools) != 1
            or tools.pop() not in {"rank_products", "analyze_regions"}
        ):
            return "排名模板FACT必须来自单一排名工具"
        if len(metrics) != 1:
            return "同一排名模板只能展示一个冻结指标"
        if ranks != list(range(1, len(ranks) + 1)):
            return "排名模板的rank必须从一开始连续"
    if template_id == "segment_comparison_finding" and any(
        fact.source_tool != "compare_segments" for fact in facts
    ):
        return "分段比较模板只能引用compare_segments FACT"
    if template_id == "customer_coverage_finding":
        required = {
            "customer_count",
            "sales_row_coverage",
            "sales_amount_coverage",
        }
        observed = {
            fact.metric
            for fact in facts
            if fact.source_tool == "analyze_customers"
        }
        if not required.issubset(observed):
            return "客户覆盖模板缺少客户数或覆盖率FACT"
    return None


def validate_semantic_report_v2_1(
    plan: SemanticReportPlanV2_1,
    facts: list[FactRecord],
) -> SemanticValidationV2_1:
    issues: list[SemanticIssueV2_1] = []
    fact_by_id = {fact.fact_id: fact for fact in facts}
    referenced: list[str] = []
    for section_index, section in enumerate(plan.sections):
        for block_index, block in enumerate(section.blocks):
            location = (
                f"sections[{section_index}].blocks[{block_index}]"
            )
            block_facts = []
            for fact_id in block.fact_ids:
                referenced.append(fact_id)
                fact = fact_by_id.get(fact_id)
                if fact is None:
                    issues.append(
                        SemanticIssueV2_1(
                            code="unknown_fact",
                            location=location,
                            message=f"FACT不存在：{fact_id}",
                        )
                    )
                    continue
                if (
                    fact.session_id != plan.session_id
                    or fact.turn_id != plan.turn_id
                ):
                    issues.append(
                        SemanticIssueV2_1(
                            code="cross_turn_fact",
                            location=location,
                            message=f"FACT不属于当前轮：{fact_id}",
                        )
                    )
                    continue
                block_facts.append(fact)
            signature_error = _signature_error(
                block.template_id,
                block_facts,
            )
            if signature_error is not None:
                issues.append(
                    SemanticIssueV2_1(
                        code="fact_signature_mismatch",
                        location=location,
                        message=signature_error,
                    )
                )
    return SemanticValidationV2_1(
        schema_version=(
            "1.5.6-h3-semantic-report-validation-v2.1"
        ),
        status="failed" if issues else "passed",
        issues=issues,
        referenced_fact_ids=list(dict.fromkeys(referenced)),
        deterministic_checks=[
            "模型不得提供自由事实叙述",
            "模板必须属于冻结章节职责",
            "FACT存在且属于当前轮",
            "峰值模板必须含peak_period及同月峰值指标",
            "排名模板必须来自单一排名工具、单一指标且rank连续",
            "客户与分段模板必须满足专用FACT签名",
            "解释、建议和限制由程序固定文本渲染",
        ],
    )


TEMPLATE_TEXT: dict[TemplateId, str] = {
    "scope_from_facts": "分析采用工具FACT记录的冻结数据口径与期间。",
    "profile_summary": "程序生成了固定数据范围与质量概况。",
    "metric_summary": "程序计算了冻结口径下的经营指标。",
    "peak_period_finding": "程序识别出所选指标的峰值完整期间。",
    "ranked_entities_finding": "程序生成了同一口径和期间内的连续排名结果。",
    "segment_comparison_finding": "程序在统一口径下生成了分段比较结果。",
    "customer_coverage_finding": "程序生成了已知客户子集的聚合指标与覆盖率。",
    "tool_evidence_summary": "以下FACT构成本轮工具证据。",
    "descriptive_only": "以上结果仅支持描述性比较，不能证明原因。",
    "verify_with_additional_data": "建议结合成本、库存、活动等额外数据后再作经营判断。",
    "data_limitations": "当前分析不支持利润、因果、预测或自动补货结论。",
}
RECIPE_TITLES: dict[RecipeId, str] = {
    "data_profile": "零售数据概况",
    "sales_overview": "零售销售概览",
    "product_ranking": "商品表现排名",
    "region_ranking": "地区表现排名",
    "peak_complete_month": "完整月份峰值分析",
    "overview_and_uk_comparison": "总体与地区分段比较",
    "peak_month_product_ranking": "峰值月份与商品表现",
    "overview_and_customer_coverage": "总体销售与客户覆盖",
}


def _evidence_line(fact: FactRecord) -> str:
    parts = [
        f"[{fact.fact_id}]",
        f"{fact.metric}={fact.display_value}",
        f"unit={fact.unit}",
        f"period={fact.analysis_scope.period}",
    ]
    if fact.analysis_scope.start_date is not None:
        parts.append(f"start={fact.analysis_scope.start_date}")
    if fact.analysis_scope.end_date is not None:
        parts.append(f"end={fact.analysis_scope.end_date}")
    if fact.dimensions:
        parts.append(
            "dimensions="
            + ",".join(
                f"{item.name}={item.value}"
                for item in fact.dimensions
            )
        )
    if fact.rank is not None:
        parts.append(f"rank={fact.rank}")
    return "；".join(parts)


def render_semantic_report_v2_1(
    plan: SemanticReportPlanV2_1,
    facts: list[FactRecord],
) -> str:
    validation = validate_semantic_report_v2_1(plan, facts)
    if validation.status != "passed":
        codes = "、".join(issue.code for issue in validation.issues)
        raise ValueError(f"语义报告校验失败：{codes}")
    fact_by_id = {fact.fact_id: fact for fact in facts}
    lines = [f"# {RECIPE_TITLES[plan.recipe_id]}", ""]
    for section in plan.sections:
        lines.extend([f"## {section.name}", ""])
        for block in section.blocks:
            lines.append(f"- {TEMPLATE_TEXT[block.template_id]}")
            for fact_id in block.fact_ids:
                lines.append(
                    f"  - 证据：{_evidence_line(fact_by_id[fact_id])}"
                )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
