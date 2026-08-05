"""Deterministic model doubles for the V2.3.4 frozen-slot boundary."""

from __future__ import annotations

from src.agent_protocol import ChartRequest, FinalReportResponse
from src.frozen_six_slot_atom_selection_v2_3_4 import (
    FrozenSlotAtomSelectionDraftV2_3_4,
    FrozenSlotAtomSelectionV2_3_4,
    FrozenSlotCatalogEnvelopeV2_3_4,
    ValidatedFrozenSlotEnvelopeV2_3_4,
)
from src.report_validation import REPORT_SECTION_ORDER, ReportClaim, ReportDraft, ReportSection


def mock_model_atom_selection(
    catalog: FrozenSlotCatalogEnvelopeV2_3_4,
) -> FrozenSlotAtomSelectionDraftV2_3_4:
    """Select IDs only; distribute factual atoms without authoring semantics."""

    factual = list(catalog.global_required_atom_ids)
    buckets = {"SLOT-002": [], "SLOT-003": [], "SLOT-004": [], "SLOT-005": []}
    for index, atom_id in enumerate(factual):
        buckets[f"SLOT-{2 + index % 4:03d}"].append(atom_id)
    selections = []
    for rule in catalog.slots:
        if rule.slot_id in buckets:
            atom_ids = buckets[rule.slot_id]
        else:
            atom_ids = list(rule.required_atom_ids)
        selections.append(
            FrozenSlotAtomSelectionV2_3_4(slot_id=rule.slot_id, atom_ids=atom_ids)
        )
    return FrozenSlotAtomSelectionDraftV2_3_4(
        phase="frozen_six_slot_atom_selection",
        session_id=catalog.session_id,
        turn_id=catalog.turn_id,
        selections=selections,
    )


def mock_model_final_report(
    envelope: ValidatedFrozenSlotEnvelopeV2_3_4,
) -> FinalReportResponse:
    section_claims: dict[str, list[ReportClaim]] = {
        name: [] for name in REPORT_SECTION_ORDER
    }
    for slot in envelope.slots:
        if not slot.support_atoms:
            statement = "本节没有可由当前确定性工具证据支持的新增结论。"
        else:
            displays = list(dict.fromkeys(atom.display_value for atom in slot.support_atoms))
            labeled = []
            for evidence in slot.allowed_evidence:
                if evidence.evidence_type == "FACT" and evidence.metric is not None:
                    value = (
                        evidence.display_value
                        if evidence.value == evidence.display_value
                        else f"{evidence.value}（{evidence.display_value}）"
                    )
                    labeled.append(f"{evidence.metric}：{value}")
                elif evidence.evidence_type == "REQUEST":
                    labeled.append(f"{evidence.parameter_name}：{evidence.value}")
                elif evidence.evidence_type == "POLICY":
                    labeled.append(evidence.message)
            statement = "可核验证据：" + "；".join(dict.fromkeys(displays + labeled)) + "。"
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
            call_id=item.call_id,
            chart_type=chart_types[item.tool_name],
            title=f"{item.tool_name} 确定性工具图表",
        )
        for item in envelope.allowed_chart_sources
        if item.tool_name in chart_types
    ]
    return FinalReportResponse(
        response_type="report",
        report=ReportDraft(
            schema_version="1.5.6-h3-report-draft-v1",
            session_id=envelope.session_id,
            turn_id=envelope.turn_id,
            title="V2.3.4 受控证据经营分析报告",
            sections=[
                ReportSection(name=name, claims=section_claims[name])
                for name in REPORT_SECTION_ORDER
            ],
        ),
        chart_requests=charts,
    )


__all__ = ["mock_model_atom_selection", "mock_model_final_report"]
