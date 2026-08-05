"""Bundle-aware offline provider doubles for V2.3.2."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from src.agent_protocol import ChartRequest, FinalReportResponse
from src.claim_evidence_bundles_v2_3_2 import (
    ClaimEvidenceEnvelopeV2_3_2,
    reference_catalog,
)
from src.deepseek_client import ChatCompletionResult, DeepSeekClientError
from src.deepseek_report_terminal_transport_mock_v2_3 import (
    FrozenNativeLogicalClientV2_3,
)
from src.deepseek_report_terminal_transport_mock_v2_3_1 import (
    OfflineDeepSeekProviderV2_3_1,
)
from src.fixed_question_validation import load_frozen_questions
from src.mock_native_tool_client_v2_1_revision import _result
from src.report_validation import (
    REPORT_SECTION_ORDER,
    ReportClaim,
    ReportDraft,
    ReportSection,
)


def _question_id(messages: list[dict[str, Any]]) -> str:
    by_text = {
        item["question"]: question_id
        for question_id, item in load_frozen_questions().items()
    }
    for message in messages:
        content = message.get("content")
        if message.get("role") == "user" and content in by_text:
            return by_text[content]
    raise DeepSeekClientError("V2.3.2 offline mock cannot identify question")


def _envelope(
    messages: list[dict[str, Any]],
) -> ClaimEvidenceEnvelopeV2_3_2 | None:
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
            == "report_terminal_claim_evidence_bundles"
        ):
            return ClaimEvidenceEnvelopeV2_3_2.model_validate(payload)
    return None


def _bundle_report(
    envelope: ClaimEvidenceEnvelopeV2_3_2,
) -> ChatCompletionResult:
    catalog = reference_catalog(envelope)
    claims = [
        ReportClaim(
            statement=(
                atom.display_value
                if atom.value == atom.display_value
                or atom.semantic_role
                not in {"metric_value", "selection_limit", "entity_rank"}
                else f"{atom.value}；{atom.display_value}"
            ),
            evidence=[catalog[item] for item in atom.evidence_ids],
        )
        for bundle in envelope.claim_evidence_bundles
        for atom in bundle.support_atoms
    ]
    if len(claims) > len(REPORT_SECTION_ORDER) * 12:
        raise DeepSeekClientError(
            "V2.3.2 bundle-aware Mock exceeds frozen report claim capacity"
        )
    section_claims: dict[str, list[ReportClaim]] = {
        name: [] for name in REPORT_SECTION_ORDER
    }
    for index, claim in enumerate(claims):
        section_claims[REPORT_SECTION_ORDER[index % len(REPORT_SECTION_ORDER)]].append(
            claim
        )
    for name in REPORT_SECTION_ORDER:
        if not section_claims[name]:
            section_claims[name].append(
                ReportClaim(statement="本节没有新增证据结论。", evidence=[])
            )
    chart_types = {
        "analyze_time_trend": "monthly_line",
        "analyze_regions": "vertical_bar",
        "rank_products": "top_n_horizontal_bar",
        "compare_segments": "two_segment_share_bar",
    }
    charts = [
        ChartRequest(
            call_id=call.internal_call_id,
            chart_type=chart_types[call.tool_name],
            title=f"{call.tool_name} 离线确定性图表",
        )
        for call in envelope.tool_evidence
        if call.tool_name in chart_types
    ]
    report = ReportDraft(
        schema_version="1.5.6-h3-report-draft-v1",
        session_id=envelope.session_id,
        turn_id=envelope.turn_id,
        title="V2.3.2 受控证据包离线报告",
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
class BundleAwareLogicalClientV2_3_2:
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
            return _bundle_report(envelope)
        return FrozenNativeLogicalClientV2_3(self.delegate).complete_json(
            messages=messages
        )


class OfflineDeepSeekProviderV2_3_2(OfflineDeepSeekProviderV2_3_1):
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
            "1.5.6-h3-v2.3.2-offline-provider-audit-v1"
        )
        payload["claim_evidence_bundles_consumed"] = True
        payload["program_authored_claim_text"] = False
        payload["real_model_called"] = False
        return payload


__all__ = [
    "BundleAwareLogicalClientV2_3_2",
    "OfflineDeepSeekProviderV2_3_2",
]
