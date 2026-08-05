"""DeepSeek transport projection for V2.3.3 plan then final report calls."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from src.controlled_claim_plan_v2_3_3 import ValidatedClaimPlanEnvelopeV2_3_3
from src.deepseek_client import DeepSeekClientError, HttpResponseData
from src.deepseek_report_terminal_transport_v2_3_2 import (
    DeepSeekReportTerminalTransportV2_3_2,
)
from src.report_admissible_evidence_projection_v2_3_1 import (
    ReportAdmissibleEnvelopeV2_3_1,
    project_terminal_messages,
)


def _json_phase(message: dict[str, Any]) -> str | None:
    if message.get("role") != "user" or not isinstance(message.get("content"), str):
        return None
    try:
        value = json.loads(message["content"])
    except json.JSONDecodeError:
        return None
    return value.get("phase") if isinstance(value, dict) else None


@dataclass
class DeepSeekControlledClaimPlanTransportV2_3_3(
    DeepSeekReportTerminalTransportV2_3_2
):
    """Project tool evidence for planning, then only validated slots for prose."""

    v2_3_3_phases: list[str] = field(default_factory=list)

    def __call__(self, url, body, headers, timeout_seconds) -> HttpResponseData:
        try:
            payload = json.loads(body.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DeepSeekClientError("V2.3.3 transport received invalid JSON") from exc
        messages = payload.get("messages") if isinstance(payload, dict) else None
        phases = (
            [_json_phase(item) for item in messages if isinstance(item, dict)]
            if isinstance(messages, list)
            else []
        )
        if "report_terminal_validated_claim_plan" in phases:
            phase = "final_report_from_validated_claim_plan"
        elif payload.get("tool_choice") == "none" and any(
            isinstance(item, dict) and item.get("role") == "tool"
            for item in (messages or [])
        ):
            phase = "controlled_claim_plan_generation"
        elif payload.get("tool_choice") == "none":
            phase = "control_response_without_claim_plan"
        else:
            phase = "business_tool_selection"
        response = super().__call__(url, body, headers, timeout_seconds)
        self.v2_3_3_phases.append(phase)
        return response

    @staticmethod
    def _project_terminal_messages(
        messages: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], int, tuple[str, ...], int, bool]:
        validated_messages = [
            item for item in messages
            if _json_phase(item) == "report_terminal_validated_claim_plan"
        ]
        if not validated_messages:
            return DeepSeekReportTerminalTransportV2_3_2._project_terminal_messages(
                messages
            )
        if len(validated_messages) != 1:
            raise DeepSeekClientError("V2.3.3 requires exactly one validated claim plan")
        try:
            validated = ValidatedClaimPlanEnvelopeV2_3_3.model_validate_json(
                validated_messages[0]["content"]
            )
        except ValueError as exc:
            raise DeepSeekClientError("V2.3.3 final claim plan failed Schema validation") from exc
        source_messages = [item for item in messages if item is not validated_messages[0]]
        projection = project_terminal_messages(source_messages)
        if not projection.terminal_evidence_envelope_added:
            raise DeepSeekClientError("V2.3.3 final report lacks current-turn tool evidence")
        source_message = projection.messages[-1]
        try:
            source = ReportAdmissibleEnvelopeV2_3_1.model_validate_json(
                source_message["content"]
            )
        except (KeyError, ValueError) as exc:
            raise DeepSeekClientError("V2.3.3 source projection is missing") from exc
        if (source.session_id, source.turn_id) != (validated.session_id, validated.turn_id):
            raise DeepSeekClientError("V2.3.3 validated plan crosses session or turn")
        clean = list(projection.messages[:-1])
        clean.append(
            {"role": "user", "content": validated.model_dump_json()}
        )
        return (
            clean,
            projection.projected_tool_message_count,
            projection.removed_tool_payload_keys,
            projection.dropped_assistant_tool_call_messages,
            True,
        )

    def audit_payload(self) -> dict[str, Any]:
        payload = super().audit_payload()
        payload["schema_version"] = (
            "1.5.6-h3-deepseek-controlled-claim-plan-transport-v2.3.3-audit-v1"
        )
        payload["controlled_claim_plan_version"] = "v2.3.3"
        payload["request_phases"] = list(self.v2_3_3_phases)
        for request, phase in zip(payload.get("requests", []), self.v2_3_3_phases):
            request["v2_3_3_phase"] = phase
        payload["program_authored_claim_text"] = False
        payload["post_hoc_report_repair"] = False
        return payload


__all__ = ["DeepSeekControlledClaimPlanTransportV2_3_3"]
