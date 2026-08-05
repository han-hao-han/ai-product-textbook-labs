"""Deterministic doubles for testing the V2.3.3 two-step report boundary."""

from __future__ import annotations

from src.agent_protocol import ChartRequest, FinalReportResponse
from src.claim_evidence_bundles_v2_3_2 import ClaimEvidenceEnvelopeV2_3_2
from src.controlled_claim_plan_v2_3_3 import (
    ClaimPlanDraftV2_3_3,
    ClaimPlanSlotDraftV2_3_3,
    ValidatedClaimPlanEnvelopeV2_3_3,
)
from src.report_validation import (
    REPORT_SECTION_ORDER,
    ReportClaim,
    ReportDraft,
    ReportSection,
)


def _slot(
    *,
    index: int,
    section_name: str,
    claim_mode: str,
    bundles: list,
) -> ClaimPlanSlotDraftV2_3_3:
    atoms = [atom for bundle in bundles for atom in bundle.support_atoms]
    return ClaimPlanSlotDraftV2_3_3(
        slot_id=f"SLOT-{index:03d}",
        section_name=section_name,
        claim_mode=claim_mode,
        atom_ids=[item.atom_id for item in atoms],
        requested_superlative_metric=None,
    )


def mock_model_claim_plan(
    source: ClaimEvidenceEnvelopeV2_3_2,
) -> ClaimPlanDraftV2_3_3:
    """Represent a model plan; it selects IDs but writes no business prose."""

    requests = [
        item for item in source.claim_evidence_bundles
        if item.bundle_kind == "request_parameter"
    ]
    policies = [
        item for item in source.claim_evidence_bundles
        if item.bundle_kind == "policy_boundary"
    ]
    data_bundles = [
        item for item in source.claim_evidence_bundles
        if item.bundle_kind not in {"request_parameter", "policy_boundary"}
    ]
    if not requests or not policies or not data_bundles:
        raise ValueError("V2.3.3 Mock requires request, policy and FACT bundles")

    sections: dict[str, list[ClaimPlanSlotDraftV2_3_3]] = {
        name: [] for name in REPORT_SECTION_ORDER
    }
    index = 0

    def add(section_name: str, claim_mode: str, bundles: list) -> None:
        nonlocal index
        index += 1
        sections[section_name].append(
            _slot(
                index=index,
                section_name=section_name,
                claim_mode=claim_mode,
                bundles=bundles,
            )
        )

    add(REPORT_SECTION_ORDER[0], "request_scope", requests)

    def mode_for(bundle_kind: str) -> str:
        return {
            "ranked_entity": "ranked_observation",
            "aggregate_metric": "aggregate_observation",
            "period_scope": "aggregate_observation",
            "cross_tool_observation": "cross_tool_observation",
        }.get(bundle_kind, "tool_method")

    for position, bundle in enumerate(data_bundles):
        section = REPORT_SECTION_ORDER[1 + (position % 2)]
        add(section, mode_for(bundle.bundle_kind), [bundle])
    if not sections[REPORT_SECTION_ORDER[1]]:
        add(REPORT_SECTION_ORDER[1], mode_for(data_bundles[0].bundle_kind), [data_bundles[0]])
    if not sections[REPORT_SECTION_ORDER[2]]:
        add(REPORT_SECTION_ORDER[2], "tool_method", [data_bundles[0]])

    interpretation_bundle = next(
        (
            item for item in data_bundles
            if item.bundle_kind == "cross_tool_observation"
        ),
        data_bundles[0],
    )
    add(REPORT_SECTION_ORDER[3], "limited_interpretation", [interpretation_bundle])

    index += 1
    sections[REPORT_SECTION_ORDER[4]].append(
        ClaimPlanSlotDraftV2_3_3(
            slot_id=f"SLOT-{index:03d}",
            section_name=REPORT_SECTION_ORDER[4],
            claim_mode="advice",
            atom_ids=[],
            requested_superlative_metric=None,
        )
    )
    add(REPORT_SECTION_ORDER[5], "policy_limit", policies)
    if any(len(value) > 12 for value in sections.values()):
        raise ValueError("V2.3.3 Mock plan exceeds frozen section capacity")
    return ClaimPlanDraftV2_3_3(
        phase="controlled_claim_plan",
        session_id=source.session_id,
        turn_id=source.turn_id,
        slots=[slot for name in REPORT_SECTION_ORDER for slot in sections[name]],
    )


def mock_model_final_report(
    plan: ValidatedClaimPlanEnvelopeV2_3_3,
) -> FinalReportResponse:
    """Represent a compliant final model response using only validated slots."""

    section_claims: dict[str, list[ReportClaim]] = {
        name: [] for name in REPORT_SECTION_ORDER
    }
    for slot in plan.slots:
        if slot.claim_mode == "advice" and not slot.support_atoms:
            statement = "建议结合业务背景，由人工复核这些确定性结果。"
        else:
            displays = list(
                dict.fromkeys(atom.display_value for atom in slot.support_atoms)
            )
            labeled_evidence: list[str] = []
            for evidence in slot.allowed_evidence:
                if evidence.evidence_type == "FACT" and evidence.metric is not None:
                    value_text = (
                        evidence.display_value
                        if evidence.value == evidence.display_value
                        else f"{evidence.value}（{evidence.display_value}）"
                    )
                    labeled_evidence.append(
                        f"{evidence.metric}：{value_text}"
                    )
                elif evidence.evidence_type == "REQUEST":
                    labeled_evidence.append(
                        f"{evidence.parameter_name}：{evidence.value}"
                    )
                elif evidence.evidence_type == "POLICY":
                    labeled_evidence.append(evidence.message)
            parts = list(dict.fromkeys(displays + labeled_evidence))
            statement = "可核验信息：" + "；".join(parts) + "。"
        section_claims[slot.section_name].append(
            ReportClaim(statement=statement, evidence=slot.allowed_evidence)
        )

    chart_types = {
        "analyze_time_trend": "monthly_line",
        "analyze_regions": "vertical_bar",
        "rank_products": "top_n_horizontal_bar",
        "compare_segments": "two_segment_share_bar",
    }
    charts = [
        ChartRequest(
            call_id=call.call_id,
            chart_type=chart_types[call.tool_name],
            title=f"{call.tool_name} 确定性工具图表",
        )
        for call in plan.allowed_chart_sources
        if call.tool_name in chart_types
    ]
    report = ReportDraft(
        schema_version="1.5.6-h3-report-draft-v1",
        session_id=plan.session_id,
        turn_id=plan.turn_id,
        title="受控证据经营分析报告",
        sections=[
            ReportSection(name=name, claims=section_claims[name])
            for name in REPORT_SECTION_ORDER
        ],
    )
    return FinalReportResponse(
        response_type="report",
        report=report,
        chart_requests=charts,
    )


__all__ = ["mock_model_claim_plan", "mock_model_final_report"]
