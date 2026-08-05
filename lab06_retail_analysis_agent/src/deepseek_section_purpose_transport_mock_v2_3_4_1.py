"""Offline providers for the integrated V2.3.4.1 candidate."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from src.deepseek_client import ChatCompletionResult
from src.deepseek_report_terminal_transport_mock_v2_3 import FrozenNativeLogicalClientV2_3
from src.deepseek_report_terminal_transport_mock_v2_3_2 import OfflineDeepSeekProviderV2_3_2
from src.mock_native_tool_client_v2_1_revision import _result
from src.section_purpose_contract_mock_v2_3_4_1 import (
    mock_model_final_report, mock_model_section_purpose_selection,
)
from src.section_purpose_contract_v2_3_4_1 import (
    SectionPurposeCatalogV2_3_4_1, ValidatedSectionPurposeEnvelopeV2_3_4_1,
)


def _phase_object(messages: list[dict[str, Any]], phase: str) -> dict[str, Any] | None:
    for message in reversed(messages):
        if message.get("role") != "user" or not isinstance(message.get("content"), str):
            continue
        try:
            value = json.loads(message["content"])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and (value.get("phase") or value.get("request_type")) == phase:
            return value
    return None


@dataclass
class SectionPurposeLogicalClientV2_3_4_1:
    delegate: Any
    selection_mutator: Callable[[dict[str, Any]], dict[str, Any]] | None = None
    report_mutator: Callable[[dict[str, Any]], dict[str, Any]] | None = None

    def complete_strict_tools(self, **kwargs: Any) -> ChatCompletionResult:
        return self.delegate.complete_strict_tools(**kwargs)

    def complete_json(self, *, messages: list[dict[str, Any]]) -> ChatCompletionResult:
        catalog_payload = _phase_object(messages, "frozen_six_slot_section_purpose_catalog")
        if catalog_payload is not None:
            catalog = SectionPurposeCatalogV2_3_4_1.model_validate(catalog_payload)
            payload = mock_model_section_purpose_selection(catalog).model_dump(mode="json")
            if self.selection_mutator is not None:
                payload = self.selection_mutator(payload)
            return _result(content=json.dumps(payload, ensure_ascii=False))
        validated_payload = _phase_object(messages, "report_terminal_validated_section_purpose_slots")
        if validated_payload is not None:
            validated = ValidatedSectionPurposeEnvelopeV2_3_4_1.model_validate(validated_payload)
            payload = mock_model_final_report(validated).model_dump(mode="json")
            if self.report_mutator is not None:
                payload = self.report_mutator(payload)
            return _result(content=json.dumps(payload, ensure_ascii=False))
        return FrozenNativeLogicalClientV2_3(self.delegate).complete_json(messages=messages)


class OfflineDeepSeekProviderV2_3_4_1(OfflineDeepSeekProviderV2_3_2):
    def audit_payload(self) -> dict[str, Any]:
        payload = super().audit_payload()
        payload["schema_version"] = "1.5.6-h3-v2.3.4.1-offline-provider-audit-v1"
        payload["section_purpose_contract_consumed"] = True
        payload["real_model_called"] = False
        return payload


__all__ = ["OfflineDeepSeekProviderV2_3_4_1", "SectionPurposeLogicalClientV2_3_4_1"]
