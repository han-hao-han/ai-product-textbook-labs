"""Offline provider doubles for the integrated V2.3.4 candidate."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from src.deepseek_client import ChatCompletionResult
from src.deepseek_report_terminal_transport_mock_v2_3 import FrozenNativeLogicalClientV2_3
from src.deepseek_report_terminal_transport_mock_v2_3_2 import OfflineDeepSeekProviderV2_3_2
from src.frozen_six_slot_atom_selection_mock_v2_3_4 import (
    mock_model_atom_selection, mock_model_final_report,
)
from src.frozen_six_slot_atom_selection_v2_3_4 import (
    FrozenSlotCatalogEnvelopeV2_3_4, ValidatedFrozenSlotEnvelopeV2_3_4,
)
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
class FrozenSixSlotLogicalClientV2_3_4:
    delegate: Any
    selection_mutator: Callable[[dict[str, Any]], dict[str, Any]] | None = None
    report_mutator: Callable[[dict[str, Any]], dict[str, Any]] | None = None

    def complete_strict_tools(self, **kwargs: Any) -> ChatCompletionResult:
        return self.delegate.complete_strict_tools(**kwargs)

    def complete_json(self, *, messages: list[dict[str, Any]]) -> ChatCompletionResult:
        catalog_payload = _phase_object(messages, "frozen_six_slot_atom_catalog")
        if catalog_payload is not None:
            catalog = FrozenSlotCatalogEnvelopeV2_3_4.model_validate(catalog_payload)
            payload = mock_model_atom_selection(catalog).model_dump(mode="json")
            if self.selection_mutator is not None:
                payload = self.selection_mutator(payload)
            return _result(content=json.dumps(payload, ensure_ascii=False))
        validated_payload = _phase_object(messages, "report_terminal_validated_frozen_slots")
        if validated_payload is not None:
            validated = ValidatedFrozenSlotEnvelopeV2_3_4.model_validate(validated_payload)
            payload = mock_model_final_report(validated).model_dump(mode="json")
            if self.report_mutator is not None:
                payload = self.report_mutator(payload)
            return _result(content=json.dumps(payload, ensure_ascii=False))
        return FrozenNativeLogicalClientV2_3(self.delegate).complete_json(messages=messages)


class OfflineDeepSeekProviderV2_3_4(OfflineDeepSeekProviderV2_3_2):
    def audit_payload(self) -> dict[str, Any]:
        payload = super().audit_payload()
        payload["schema_version"] = "1.5.6-h3-v2.3.4-offline-provider-audit-v1"
        payload["frozen_six_slot_atom_selection_consumed"] = True
        payload["real_model_called"] = False
        return payload


__all__ = ["FrozenSixSlotLogicalClientV2_3_4", "OfflineDeepSeekProviderV2_3_4"]
