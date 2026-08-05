"""Offline provider doubles for the V2.3.1 admissible-evidence wire form."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from src.agent_protocol import ChartRequest, FinalReportResponse
from src.deepseek_client import ChatCompletionResult, DeepSeekClientError
from src.deepseek_report_terminal_transport_mock_v2_3 import (
    FrozenNativeLogicalClientV2_3,
    OfflineDeepSeekProviderV2_3,
)
from src.fixed_question_validation import load_frozen_questions
from src.mock_native_tool_client_v2_1_revision import _result
from src.report_admissible_evidence_projection_v2_3_1 import (
    ReportAdmissibleEnvelopeV2_3_1,
)
from src.report_validation import (
    REPORT_SECTION_ORDER,
    ReportClaim,
    ReportDraft,
    ReportFactReference,
    ReportPolicyReference,
    ReportRequestReference,
    ReportSection,
)


def _question_id(messages: list[dict[str, Any]]) -> str:
    by_text = {
        item["question"]: question_id
        for question_id, item in load_frozen_questions().items()
    }
    for message in messages:
        if message.get("role") == "user" and message.get("content") in by_text:
            return by_text[message["content"]]
    raise DeepSeekClientError("V2.3.1 offline mock cannot identify question")


def _envelope(
    messages: list[dict[str, Any]],
) -> ReportAdmissibleEnvelopeV2_3_1 | None:
    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if not isinstance(content, str):
            continue
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            continue
        if (
            isinstance(payload, dict)
            and payload.get("phase")
            == "report_terminal_admissible_evidence"
        ):
            return ReportAdmissibleEnvelopeV2_3_1.model_validate(payload)
    return None


def _reference_claim(reference: Any) -> ReportClaim:
    if isinstance(reference, ReportFactReference):
        parts = [
            *(item.value for item in reference.dimensions),
            reference.value,
            reference.display_value,
            reference.period,
        ]
        if reference.rank is not None:
            parts.append(str(reference.rank))
        if reference.start_date is not None:
            parts.append(reference.start_date)
        if reference.end_date is not None:
            parts.append(reference.end_date)
        statement = "；".join(dict.fromkeys(parts))
    elif isinstance(reference, ReportRequestReference):
        statement = f"{reference.parameter_name}：{reference.value}"
    elif isinstance(reference, ReportPolicyReference):
        statement = reference.message
    else:  # pragma: no cover - guarded by Pydantic envelope validation
        raise DeepSeekClientError("unsupported report reference type")
    return ReportClaim(statement=statement, evidence=[reference])


def _report_response(
    messages: list[dict[str, Any]],
    envelope: ReportAdmissibleEnvelopeV2_3_1,
) -> ChatCompletionResult:
    del messages
    references: dict[str, Any] = {}
    chart_types = {
        "analyze_time_trend": "monthly_line",
        "analyze_regions": "vertical_bar",
        "rank_products": "top_n_horizontal_bar",
        "compare_segments": "two_segment_share_bar",
    }
    charts: list[ChartRequest] = []
    for call in envelope.tool_evidence:
        for reference in call.fact_references:
            references[reference.fact_id] = reference
        for reference in call.request_references:
            references[reference.request_id] = reference
        for reference in call.policy_references:
            references[reference.policy_id] = reference
        chart_type = chart_types.get(call.tool_name)
        if chart_type is not None:
            charts.append(
                ChartRequest(
                    call_id=call.internal_call_id,
                    chart_type=chart_type,
                    title=f"{call.tool_name} 离线确定性图表",
                )
            )
    evidence_claims = [_reference_claim(item) for item in references.values()]
    if len(evidence_claims) > len(REPORT_SECTION_ORDER) * 12:
        raise DeepSeekClientError(
            "V2.3.1 offline report exceeds frozen claim capacity"
        )
    section_claims: dict[str, list[ReportClaim]] = {
        name: [] for name in REPORT_SECTION_ORDER
    }
    for index, claim in enumerate(evidence_claims):
        section_claims[REPORT_SECTION_ORDER[index % len(REPORT_SECTION_ORDER)]].append(
            claim
        )
    for name in REPORT_SECTION_ORDER:
        if not section_claims[name]:
            section_claims[name].append(
                ReportClaim(statement="本节没有新增证据结论。", evidence=[])
            )
    report = ReportDraft(
        schema_version="1.5.6-h3-report-draft-v1",
        session_id=envelope.session_id,
        turn_id=envelope.turn_id,
        title="离线报告可引用证据验证",
        sections=[
            ReportSection(name=name, claims=section_claims[name])
            for name in REPORT_SECTION_ORDER
        ],
    )
    return _result(
        content=FinalReportResponse(
            response_type="report",
            report=report,
            chart_requests=charts,
        ).model_dump_json()
    )


@dataclass
class ReportAdmissibleLogicalClientV2_3_1:
    """Consume the exact projected wire form without reconstructing FACTs."""

    delegate: Any

    def complete_strict_tools(self, **kwargs: Any) -> ChatCompletionResult:
        return self.delegate.complete_strict_tools(**kwargs)

    def complete_json(
        self,
        *,
        messages: list[dict[str, Any]],
    ) -> ChatCompletionResult:
        _question_id(messages)
        envelope = _envelope(messages)
        if envelope is not None:
            return _report_response(messages, envelope)
        return FrozenNativeLogicalClientV2_3(self.delegate).complete_json(
            messages=messages
        )


class OfflineDeepSeekProviderV2_3_1(OfflineDeepSeekProviderV2_3):
    """Version label for audits; wire validation remains V2.3-compatible."""

    @staticmethod
    def _terminal_evidence_call_keys(
        messages: list[dict[str, Any]],
    ) -> tuple[tuple[str, ...], ...]:
        envelope = _envelope(messages)
        if envelope is None:
            return ()
        return tuple(
            tuple(sorted(call.model_dump(mode="json")))
            for call in envelope.tool_evidence
        )

    def audit_payload(self) -> dict[str, Any]:
        payload = super().audit_payload()
        payload["schema_version"] = (
            "1.5.6-h3-v2.3.1-offline-provider-audit-v1"
        )
        payload["report_admissible_projection_consumed"] = True
        return payload


__all__ = [
    "OfflineDeepSeekProviderV2_3_1",
    "ReportAdmissibleLogicalClientV2_3_1",
]
