"""V3.1 controlled templates for narrative claims and report titles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.agent_protocol import FinalReportResponse
from src.claim_level_report_controller_v3 import (
    ClaimControllerContextV3,
    ClaimControllerValidationError,
    ClaimStatementResponseV3,
    assemble_final_report_v3,
)
from src.section_purpose_contract_v2_3_4_1 import (
    ValidatedSectionPurposeEnvelopeV2_3_4_1,
)


PHASE_V3_1 = "report_terminal_claim_and_template_plan_v3_1"
RESPONSE_PHASE_V3_1 = "claim_and_template_selection_response_v3_1"

REPORT_TITLE_TEMPLATES = {
    "TITLE-CONTROLLED-RETAIL": "受控证据零售经营分析报告",
    "TITLE-DETERMINISTIC-BUSINESS": "确定性工具经营分析报告",
}
INTERPRETATION_TEMPLATES = {
    "INTERPRET-HISTORICAL-ONLY": (
        "该结果仅反映所选历史数据的描述性表现，具体业务含义需要人工结合背景判断。"
    ),
    "INTERPRET-NO-CAUSE-OR-FORECAST": (
        "当前证据支持描述结果，但不支持因果解释或未来趋势判断。"
    ),
}
RECOMMENDATION_TEMPLATES = {
    "RECOMMEND-HUMAN-REVIEW": (
        "建议由人工复核工具结果并结合业务背景决定后续行动。"
    ),
    "RECOMMEND-FOLLOWUP-ANALYSIS": (
        "建议在保持当前分析口径的前提下，由人工决定是否开展后续分析。"
    ),
}
CHART_TITLE_TEMPLATES = {
    "analyze_time_trend": {
        "CHART-TIME-TREND": "月度经营趋势",
        "CHART-TIME-COMPARISON": "月度指标对比",
    },
    "analyze_regions": {
        "CHART-REGION-OVERVIEW": "地区经营概览",
        "CHART-REGION-COMPARISON": "地区指标对比",
    },
    "rank_products": {
        "CHART-PRODUCT-RANKING": "商品经营排名",
        "CHART-PRODUCT-COMPARISON": "商品指标对比",
    },
    "compare_segments": {
        "CHART-SEGMENT-OVERVIEW": "客户分群概览",
        "CHART-SEGMENT-COMPARISON": "客户分群对比",
    },
}


class StrictTemplateModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class AuthoredClaimPlanV3_1(StrictTemplateModel):
    claim_id: str = Field(pattern=r"^CLAIM-\d{3,}$")
    slot_id: str = Field(pattern=r"^SLOT-00[1236]$")
    section_name: str
    purpose: str
    required_literals: list[str] = Field(max_length=40)


class TemplateClaimPlanV3_1(StrictTemplateModel):
    claim_id: str = Field(pattern=r"^CLAIM-\d{3,}$")
    slot_id: Literal["SLOT-004", "SLOT-005"]
    section_name: str
    allowed_template_ids: list[str] = Field(min_length=1, max_length=10)


class ChartTemplatePlanV3_1(StrictTemplateModel):
    chart_plan_id: str = Field(pattern=r"^CHART-\d{3,}$")
    tool_name: str
    chart_type: str
    allowed_title_template_ids: list[str] = Field(min_length=1, max_length=10)


class ClaimTemplatePlanEnvelopeV3_1(StrictTemplateModel):
    phase: Literal["report_terminal_claim_and_template_plan_v3_1"]
    session_id: str = Field(pattern=r"^SESSION-[A-Za-z0-9_-]+$")
    turn_id: str = Field(pattern=r"^TURN-\d{3,}$")
    allowed_report_title_template_ids: list[str] = Field(min_length=1, max_length=10)
    authored_claims: list[AuthoredClaimPlanV3_1] = Field(min_length=1, max_length=70)
    template_claims: list[TemplateClaimPlanV3_1] = Field(min_length=2, max_length=2)
    chart_plans: list[ChartTemplatePlanV3_1] = Field(max_length=4)
    instruction: str

    @model_validator(mode="after")
    def validate_claim_partition(self) -> "ClaimTemplatePlanEnvelopeV3_1":
        all_ids = [item.claim_id for item in self.authored_claims + self.template_claims]
        if len(all_ids) != len(set(all_ids)):
            raise ValueError("authored and template claims must be disjoint")
        if [item.slot_id for item in self.template_claims] != ["SLOT-004", "SLOT-005"]:
            raise ValueError("template claims must be the interpretation and recommendation slots")
        return self


class AuthoredClaimResponseV3_1(StrictTemplateModel):
    claim_id: str = Field(pattern=r"^CLAIM-\d{3,}$")
    statement: str = Field(min_length=1, max_length=1000)


class ClaimTemplateSelectionV3_1(StrictTemplateModel):
    claim_id: str = Field(pattern=r"^CLAIM-\d{3,}$")
    template_id: str = Field(min_length=1, max_length=100)


class ChartTitleTemplateSelectionV3_1(StrictTemplateModel):
    chart_plan_id: str = Field(pattern=r"^CHART-\d{3,}$")
    title_template_id: str = Field(min_length=1, max_length=100)


class ClaimTemplateResponseV3_1(StrictTemplateModel):
    phase: Literal["claim_and_template_selection_response_v3_1"]
    session_id: str = Field(pattern=r"^SESSION-[A-Za-z0-9_-]+$")
    turn_id: str = Field(pattern=r"^TURN-\d{3,}$")
    report_title_template_id: str = Field(min_length=1, max_length=100)
    authored_claims: list[AuthoredClaimResponseV3_1] = Field(min_length=1, max_length=70)
    template_selections: list[ClaimTemplateSelectionV3_1] = Field(min_length=2, max_length=2)
    chart_title_selections: list[ChartTitleTemplateSelectionV3_1] = Field(max_length=4)


@dataclass(frozen=True)
class ClaimTemplateContextV3_1:
    model_visible: ClaimTemplatePlanEnvelopeV3_1
    base: ClaimControllerContextV3


def build_claim_template_context_v3_1(
    base: ClaimControllerContextV3,
) -> ClaimTemplateContextV3_1:
    authored = []
    templated = []
    for visible in base.model_visible.claims:
        if visible.slot_id == "SLOT-004":
            templated.append(
                TemplateClaimPlanV3_1(
                    claim_id=visible.claim_id,
                    slot_id="SLOT-004",
                    section_name=visible.section_name,
                    allowed_template_ids=list(INTERPRETATION_TEMPLATES),
                )
            )
        elif visible.slot_id == "SLOT-005":
            templated.append(
                TemplateClaimPlanV3_1(
                    claim_id=visible.claim_id,
                    slot_id="SLOT-005",
                    section_name=visible.section_name,
                    allowed_template_ids=list(RECOMMENDATION_TEMPLATES),
                )
            )
        else:
            authored.append(
                AuthoredClaimPlanV3_1(
                    claim_id=visible.claim_id,
                    slot_id=visible.slot_id,
                    section_name=visible.section_name,
                    purpose=visible.purpose,
                    required_literals=visible.required_literals,
                )
            )
    chart_plans = []
    for chart in base.model_visible.chart_plans:
        templates = CHART_TITLE_TEMPLATES.get(chart.tool_name)
        if not templates:
            raise ClaimControllerValidationError(
                "chart_title_template_missing",
                f"no chart title template is frozen for {chart.tool_name}",
            )
        chart_plans.append(
            ChartTemplatePlanV3_1(
                chart_plan_id=chart.chart_plan_id,
                tool_name=chart.tool_name,
                chart_type=chart.chart_type,
                allowed_title_template_ids=list(templates),
            )
        )
    envelope = ClaimTemplatePlanEnvelopeV3_1(
        phase=PHASE_V3_1,
        session_id=base.model_visible.session_id,
        turn_id=base.model_visible.turn_id,
        allowed_report_title_template_ids=list(REPORT_TITLE_TEMPLATES),
        authored_claims=authored,
        template_claims=templated,
        chart_plans=chart_plans,
        instruction=(
            "Write only authored_claims. Select one allowed template ID for the report title, "
            "each template claim, and each chart title. Return every supplied ID in order."
        ),
    )
    return ClaimTemplateContextV3_1(envelope, base)


def expand_claim_template_response_v3_1(
    response: ClaimTemplateResponseV3_1,
    context: ClaimTemplateContextV3_1,
    validated: ValidatedSectionPurposeEnvelopeV2_3_4_1,
) -> FinalReportResponse:
    plan = context.model_visible
    issues: list[dict] = []
    if (response.session_id, response.turn_id) != (plan.session_id, plan.turn_id):
        issues.append({"code": "cross_turn_template_response", "location": "response"})
    expected_authored = [item.claim_id for item in plan.authored_claims]
    if [item.claim_id for item in response.authored_claims] != expected_authored:
        issues.append({"code": "authored_claim_id_order_mismatch", "location": "authored_claims"})
    expected_templates = [item.claim_id for item in plan.template_claims]
    if [item.claim_id for item in response.template_selections] != expected_templates:
        issues.append({"code": "template_claim_id_order_mismatch", "location": "template_selections"})
    expected_charts = [item.chart_plan_id for item in plan.chart_plans]
    if [item.chart_plan_id for item in response.chart_title_selections] != expected_charts:
        issues.append({"code": "chart_template_id_order_mismatch", "location": "chart_title_selections"})
    if response.report_title_template_id not in plan.allowed_report_title_template_ids:
        issues.append({"code": "report_title_template_not_allowed", "location": "report_title_template_id"})
    allowed_claim_templates = {
        item.claim_id: set(item.allowed_template_ids) for item in plan.template_claims
    }
    for index, item in enumerate(response.template_selections):
        if item.template_id not in allowed_claim_templates.get(item.claim_id, set()):
            issues.append({"code": "claim_template_not_allowed", "location": f"template_selections[{index}]"})
    allowed_chart_templates = {
        item.chart_plan_id: set(item.allowed_title_template_ids) for item in plan.chart_plans
    }
    for index, item in enumerate(response.chart_title_selections):
        if item.title_template_id not in allowed_chart_templates.get(item.chart_plan_id, set()):
            issues.append({"code": "chart_title_template_not_allowed", "location": f"chart_title_selections[{index}]"})
    if issues:
        raise ClaimControllerValidationError(
            "template_selection_validation_failed",
            "model template selections differ from the frozen plan",
            issues=issues,
        )

    authored = {item.claim_id: item.statement for item in response.authored_claims}
    selected_templates = {item.claim_id: item.template_id for item in response.template_selections}
    statements = []
    for item in context.base.claims:
        if item.slot_id == "SLOT-004":
            statement = INTERPRETATION_TEMPLATES[selected_templates[item.claim_id]]
        elif item.slot_id == "SLOT-005":
            statement = RECOMMENDATION_TEMPLATES[selected_templates[item.claim_id]]
        else:
            statement = authored[item.claim_id]
        statements.append({"claim_id": item.claim_id, "statement": statement})
    chart_selection = {
        item.chart_plan_id: item.title_template_id
        for item in response.chart_title_selections
    }
    chart_titles = []
    for item in context.base.charts:
        template_id = chart_selection[item.chart_plan_id]
        chart_titles.append(
            {
                "chart_plan_id": item.chart_plan_id,
                "title": CHART_TITLE_TEMPLATES[item.tool_name][template_id],
            }
        )
    expanded = ClaimStatementResponseV3(
        phase="claim_statement_response_v3",
        session_id=response.session_id,
        turn_id=response.turn_id,
        title=REPORT_TITLE_TEMPLATES[response.report_title_template_id],
        claims=statements,
        chart_titles=chart_titles,
    )
    return assemble_final_report_v3(expanded, context.base, validated)


def build_repair_feedback_v3_1(
    *,
    context: ClaimTemplateContextV3_1,
    issues: list[dict],
    repair_attempt: int,
) -> dict:
    """Give one deterministic, claim-local correction contract."""
    return {
        "phase": "claim_template_validation_feedback_v3_1",
        "repair_attempt": repair_attempt,
        "issues": issues,
        "authored_claim_contracts": [
            {
                "claim_id": item.claim_id,
                "required_literals_exact": item.required_literals,
                "rule": (
                    "copy every required literal character-for-character; do not translate; "
                    "do not add numbers, dates, metrics or results from another claim"
                ),
            }
            for item in context.model_visible.authored_claims
        ],
        "instruction": (
            "Return the complete corrected V3.1 response. Preserve all IDs and order. "
            "For a missing-literal claim, use a short sentence containing its exact required "
            "literals and no borrowed values. Select only allowed template IDs."
        ),
    }


__all__ = [
    "CHART_TITLE_TEMPLATES", "ClaimTemplateContextV3_1",
    "ClaimTemplatePlanEnvelopeV3_1", "ClaimTemplateResponseV3_1",
    "INTERPRETATION_TEMPLATES", "REPORT_TITLE_TEMPLATES",
    "RECOMMENDATION_TEMPLATES", "build_claim_template_context_v3_1",
    "build_repair_feedback_v3_1", "expand_claim_template_response_v3_1",
]
