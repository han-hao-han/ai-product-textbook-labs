"""Offline provider doubles for the V2.3.4.2 isolated terminal protocol."""

from __future__ import annotations

import json
import calendar
from dataclasses import dataclass
from typing import Any, Callable

from src.agent_protocol import ChartRequest, FinalReportResponse
from src.deepseek_client import ChatCompletionResult
from src.deepseek_report_terminal_transport_mock_v2_3 import (
    FrozenNativeLogicalClientV2_3,
)
from src.deepseek_report_terminal_transport_mock_v2_3_2 import (
    OfflineDeepSeekProviderV2_3_2,
)
from src.mock_native_tool_client_v2_1_revision import _result
from src.mock_native_tool_client_v2_1_revision import (
    FrozenQuestionNativeToolMockClient,
)
from src.fixed_question_validation import load_frozen_questions
from src.report_terminal_protocol_guard_v2_3_4_2 import (
    ModelChartRequestV2_3_4_2,
    ModelFinalReportResponseV2_3_4_2,
    ValidatedModelVisibleEnvelopeV2_3_4_2,
)
from src.report_validation import ReportClaim, ReportDraft, ReportSection
from src.section_purpose_contract_mock_v2_3_4_1 import (
    mock_model_section_purpose_selection,
)
from src.section_purpose_contract_v2_3_4_1 import (
    SectionPurposeCatalogV2_3_4_1,
)


def _phase_object(
    messages: list[dict[str, Any]], phase: str
) -> dict[str, Any] | None:
    for message in reversed(messages):
        if message.get("role") != "user" or not isinstance(
            message.get("content"), str
        ):
            continue
        try:
            value = json.loads(message["content"])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and (
            value.get("phase") or value.get("request_type")
        ) == phase:
            return value
    return None


def mock_model_alias_report(
    envelope: ValidatedModelVisibleEnvelopeV2_3_4_2,
) -> ModelFinalReportResponseV2_3_4_2:
    sections: list[ReportSection] = []
    for slot in envelope.slots:
        claims: list[ReportClaim] = []
        current_labels: list[str] = []
        current_evidence = []
        for evidence in slot.allowed_evidence:
            if evidence.evidence_type == "FACT" and evidence.metric is not None:
                value = (
                    evidence.display_value
                    if evidence.value == evidence.display_value
                    else f"{evidence.value}（{evidence.display_value}）"
                )
                dimensions = "，".join(
                    item.value for item in evidence.dimensions
                )
                label = f"{evidence.metric}: {value}"
                if dimensions:
                    label += f"，{dimensions}"
            elif evidence.evidence_type == "REQUEST":
                label = f"{evidence.parameter_name}: {evidence.value}"
            else:
                label = evidence.message
            candidate = "可核验证据：" + "；".join(current_labels + [label]) + "。"
            if current_labels and len(candidate) > 850:
                claims.append(
                    ReportClaim(
                        statement="可核验证据：" + "；".join(current_labels) + "。",
                        evidence=current_evidence,
                    )
                )
                current_labels = []
                current_evidence = []
            current_labels.append(label)
            current_evidence.append(evidence)
        if current_labels:
            claims.append(
                ReportClaim(
                    statement="可核验证据：" + "；".join(current_labels) + "。",
                    evidence=current_evidence,
                )
            )
        if not claims:
            claims = [
                ReportClaim(
                    statement="本节没有可由当前确定性工具证据支持的新增结论。",
                    evidence=[],
                )
            ]
        sections.append(
            ReportSection(
                name=slot.section_name,
                claims=claims,
            )
        )
    return ModelFinalReportResponseV2_3_4_2(
        response_type="report",
        report=ReportDraft(
            schema_version="1.5.6-h3-report-draft-v1",
            session_id=envelope.session_id,
            turn_id=envelope.turn_id,
            title="V2.3.4.2 受控证据经营分析报告",
            sections=sections,
        ),
        chart_requests=[
            ModelChartRequestV2_3_4_2(
                chart_source_key=item.chart_source_key,
                chart_type=item.allowed_chart_types[0],
                title=f"{item.tool_name} 确定性工具图表",
            )
            for item in envelope.allowed_chart_sources
        ],
    )


@dataclass
class CallIsolatedFrozenQuestionNativeToolMockClient(
    FrozenQuestionNativeToolMockClient
):
    """Model double whose Q06 decision uses only model-visible FACT fields."""

    def complete_strict_tools(self, **kwargs: Any) -> ChatCompletionResult:
        messages = kwargs["messages"]
        user_question = next(
            item["content"] for item in messages if item.get("role") == "user"
        )
        question_by_text = {
            item["question"]: question_id
            for question_id, item in load_frozen_questions().items()
        }
        payloads = [
            json.loads(item["content"])
            for item in messages
            if item.get("role") == "tool"
        ]
        if question_by_text.get(user_question) == "Q06" and len(payloads) == 1:
            self.call_count += 1
            peak = next(
                fact["value"]
                for fact in payloads[0]["facts"]
                if fact.get("metric") == "peak_period"
            )
            year, month = map(int, peak.split("-"))
            last_day = calendar.monthrange(year, month)[1]
            return _result(
                tool_name="rank_products",
                arguments={
                    "period": "custom",
                    "start_date": f"{peak}-01",
                    "end_date": f"{peak}-{last_day:02d}",
                    "metric": "sales_amount",
                    "top_n": 3,
                },
                call_index=self.call_count,
            )
        return super().complete_strict_tools(**kwargs)


@dataclass
class CallIsolatedLogicalClientV2_3_4_2:
    delegate: Any
    selection_mutator: Callable[[dict[str, Any]], dict[str, Any]] | None = None
    report_mutator: Callable[[dict[str, Any]], dict[str, Any]] | None = None

    def complete_strict_tools(self, **kwargs: Any) -> ChatCompletionResult:
        return self.delegate.complete_strict_tools(**kwargs)

    def complete_json(
        self, *, messages: list[dict[str, Any]]
    ) -> ChatCompletionResult:
        catalog_payload = _phase_object(
            messages, "frozen_six_slot_section_purpose_catalog"
        )
        if catalog_payload is not None:
            catalog = SectionPurposeCatalogV2_3_4_1.model_validate(
                catalog_payload
            )
            payload = mock_model_section_purpose_selection(catalog).model_dump(
                mode="json"
            )
            if self.selection_mutator is not None:
                payload = self.selection_mutator(payload)
            return _result(content=json.dumps(payload, ensure_ascii=False))
        validated_payload = _phase_object(
            messages,
            "report_terminal_validated_section_purpose_slots_v2_3_4_2",
        )
        if validated_payload is not None:
            validated = ValidatedModelVisibleEnvelopeV2_3_4_2.model_validate(
                validated_payload
            )
            payload = mock_model_alias_report(validated).model_dump(mode="json")
            if self.report_mutator is not None:
                payload = self.report_mutator(payload)
            return _result(content=json.dumps(payload, ensure_ascii=False))
        return FrozenNativeLogicalClientV2_3(self.delegate).complete_json(
            messages=messages
        )


class OfflineDeepSeekProviderV2_3_4_2(OfflineDeepSeekProviderV2_3_2):
    def audit_payload(self) -> dict[str, Any]:
        payload = super().audit_payload()
        payload["schema_version"] = (
            "1.5.6-h3-v2.3.4.2-offline-provider-audit-v1"
        )
        payload["internal_call_id_seen"] = False
        payload["real_model_called"] = False
        return payload


__all__ = [
    "CallIsolatedFrozenQuestionNativeToolMockClient",
    "CallIsolatedLogicalClientV2_3_4_2",
    "OfflineDeepSeekProviderV2_3_4_2",
    "mock_model_alias_report",
]
