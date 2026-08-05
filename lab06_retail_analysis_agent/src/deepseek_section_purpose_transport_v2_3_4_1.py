"""DeepSeek transport for V2.3.4.1 section-purpose selection and reporting."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from src.deepseek_client import DeepSeekClientError, HttpResponseData
from src.deepseek_frozen_six_slot_transport_v2_3_4 import DeepSeekFrozenSixSlotTransportV2_3_4
from src.deepseek_report_terminal_transport_v2_3_2 import DeepSeekReportTerminalTransportV2_3_2
from src.report_admissible_evidence_projection_v2_3_1 import (
    ReportAdmissibleEnvelopeV2_3_1, project_terminal_messages,
)
from src.section_purpose_contract_v2_3_4_1 import ValidatedSectionPurposeEnvelopeV2_3_4_1


def _json_phase(message: dict[str, Any]) -> str | None:
    if message.get("role") != "user" or not isinstance(message.get("content"), str):
        return None
    try:
        value = json.loads(message["content"])
    except json.JSONDecodeError:
        return None
    if not isinstance(value, dict):
        return None
    return value.get("phase") or value.get("request_type")


@dataclass
class DeepSeekSectionPurposeTransportV2_3_4_1(DeepSeekFrozenSixSlotTransportV2_3_4):
    v2_3_4_1_phases: list[str] = field(default_factory=list)

    def __call__(self, url, body, headers, timeout_seconds) -> HttpResponseData:
        try:
            payload = json.loads(body.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DeepSeekClientError("V2.3.4.1 transport received invalid JSON") from exc
        messages = payload.get("messages") if isinstance(payload, dict) else []
        phases = [_json_phase(item) for item in messages if isinstance(item, dict)]
        if "report_terminal_validated_section_purpose_slots" in phases:
            phase = "final_report_from_section_purpose_slots"
        elif "frozen_six_slot_section_purpose_catalog" in phases:
            phase = "section_purpose_atom_selection"
        elif payload.get("tool_choice") == "none":
            phase = "control_response_without_section_purpose"
        else:
            phase = "business_tool_selection"
        response = super().__call__(url, body, headers, timeout_seconds)
        self.v2_3_4_1_phases.append(phase)
        return response

    @staticmethod
    def _project_terminal_messages(messages: list[dict[str, Any]]):
        validated_messages = [
            item for item in messages
            if _json_phase(item) == "report_terminal_validated_section_purpose_slots"
        ]
        catalog_messages = [
            item for item in messages
            if _json_phase(item) == "frozen_six_slot_section_purpose_catalog"
        ]
        if catalog_messages and not validated_messages:
            if len(catalog_messages) != 1:
                raise DeepSeekClientError("V2.3.4.1 requires exactly one purpose catalog")
            return list(messages), 0, (), 0, True
        if not validated_messages:
            return DeepSeekReportTerminalTransportV2_3_2._project_terminal_messages(messages)
        if len(validated_messages) != 1:
            raise DeepSeekClientError("V2.3.4.1 requires exactly one validated purpose envelope")
        try:
            validated = ValidatedSectionPurposeEnvelopeV2_3_4_1.model_validate_json(
                validated_messages[0]["content"]
            )
        except ValueError as exc:
            raise DeepSeekClientError("V2.3.4.1 final envelope failed Schema validation") from exc
        source_messages = [item for item in messages if item is not validated_messages[0]]
        projection = project_terminal_messages(source_messages)
        if not projection.terminal_evidence_envelope_added:
            raise DeepSeekClientError("V2.3.4.1 final report lacks current-turn evidence")
        try:
            source = ReportAdmissibleEnvelopeV2_3_1.model_validate_json(
                projection.messages[-1]["content"]
            )
        except (KeyError, ValueError) as exc:
            raise DeepSeekClientError("V2.3.4.1 source projection is missing") from exc
        if (source.session_id, source.turn_id) != (validated.session_id, validated.turn_id):
            raise DeepSeekClientError("V2.3.4.1 validated slots cross session or turn")
        clean = list(projection.messages[:-1])
        clean.append({"role": "user", "content": validated.model_dump_json()})
        return (
            clean, projection.projected_tool_message_count,
            projection.removed_tool_payload_keys,
            projection.dropped_assistant_tool_call_messages, True,
        )

    def audit_payload(self) -> dict[str, Any]:
        payload = super().audit_payload()
        payload["schema_version"] = "1.5.6-h3-section-purpose-transport-v2.3.4.1-audit-v1"
        payload["section_purpose_contract_version"] = "v2.3.4.1"
        payload["request_phases"] = list(self.v2_3_4_1_phases)
        for request, phase in zip(payload.get("requests", []), self.v2_3_4_1_phases):
            request["v2_3_4_1_phase"] = phase
        payload["model_authored_structure"] = False
        payload["program_authored_claim_text"] = False
        payload["formal_report_validator_changed"] = False
        return payload


__all__ = ["DeepSeekSectionPurposeTransportV2_3_4_1"]
