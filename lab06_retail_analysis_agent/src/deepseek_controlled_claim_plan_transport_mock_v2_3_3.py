"""Offline provider doubles for the integrated V2.3.3 candidate."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from src.agent_protocol import FinalReportResponse
from src.claim_evidence_bundles_v2_3_2 import ClaimEvidenceEnvelopeV2_3_2
from src.controlled_claim_plan_mock_v2_3_3 import (
    mock_model_claim_plan,
    mock_model_final_report,
)
from src.controlled_claim_plan_v2_3_3 import ValidatedClaimPlanEnvelopeV2_3_3
from src.deepseek_client import ChatCompletionResult, DeepSeekClientError
from src.deepseek_report_terminal_transport_mock_v2_3 import FrozenNativeLogicalClientV2_3
from src.deepseek_report_terminal_transport_mock_v2_3_2 import OfflineDeepSeekProviderV2_3_2
from src.mock_native_tool_client_v2_1_revision import _result


def _phase_object(messages: list[dict[str, Any]], phase: str) -> dict[str, Any] | None:
    for message in reversed(messages):
        if message.get("role") != "user" or not isinstance(message.get("content"), str):
            continue
        try:
            value = json.loads(message["content"])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and value.get("phase") == phase:
            return value
    return None


@dataclass
class ControlledClaimPlanLogicalClientV2_3_3:
    delegate: Any
    plan_mutator: Callable[[dict[str, Any]], dict[str, Any]] | None = None

    def complete_strict_tools(self, **kwargs: Any) -> ChatCompletionResult:
        return self.delegate.complete_strict_tools(**kwargs)

    def complete_json(self, *, messages: list[dict[str, Any]]) -> ChatCompletionResult:
        source_payload = _phase_object(messages, "report_terminal_claim_evidence_bundles")
        if source_payload is not None:
            source = ClaimEvidenceEnvelopeV2_3_2.model_validate(source_payload)
            payload = mock_model_claim_plan(source).model_dump(mode="json")
            if self.plan_mutator is not None:
                payload = self.plan_mutator(payload)
            return _result(content=json.dumps(payload, ensure_ascii=False))
        validated_payload = _phase_object(messages, "report_terminal_validated_claim_plan")
        if validated_payload is not None:
            validated = ValidatedClaimPlanEnvelopeV2_3_3.model_validate(validated_payload)
            final: FinalReportResponse = mock_model_final_report(validated)
            return _result(content=final.model_dump_json())
        return FrozenNativeLogicalClientV2_3(self.delegate).complete_json(messages=messages)


class OfflineDeepSeekProviderV2_3_3(OfflineDeepSeekProviderV2_3_2):
    def audit_payload(self) -> dict[str, Any]:
        payload = super().audit_payload()
        payload["schema_version"] = "1.5.6-h3-v2.3.3-offline-provider-audit-v1"
        payload["controlled_claim_plan_consumed"] = True
        payload["real_model_called"] = False
        return payload


__all__ = [
    "ControlledClaimPlanLogicalClientV2_3_3",
    "OfflineDeepSeekProviderV2_3_3",
]
