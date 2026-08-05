"""Offline model double for the V3.1 claim/template controller."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from src.claim_level_report_controller_mock_v3 import ClaimLevelLogicalClientV3
from src.claim_level_report_controller_v3_1 import (
    PHASE_V3_1,
    RESPONSE_PHASE_V3_1,
    ClaimTemplatePlanEnvelopeV3_1,
    ClaimTemplateResponseV3_1,
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


def mock_claim_template_response_v3_1(
    envelope: ClaimTemplatePlanEnvelopeV3_1,
) -> ClaimTemplateResponseV3_1:
    payload = {
        "phase": RESPONSE_PHASE_V3_1,
        "session_id": envelope.session_id,
        "turn_id": envelope.turn_id,
        "report_title_template_id": envelope.allowed_report_title_template_ids[0],
        "authored_claims": [
            {
                "claim_id": item.claim_id,
                "statement": (
                    "；".join(item.required_literals) + "。"
                    if item.required_literals
                    else "本节说明结论由确定性工具和共享数据支持。"
                ),
            }
            for item in envelope.authored_claims
        ],
        "template_selections": [
            {
                "claim_id": item.claim_id,
                "template_id": item.allowed_template_ids[0],
            }
            for item in envelope.template_claims
        ],
        "chart_title_selections": [
            {
                "chart_plan_id": item.chart_plan_id,
                "title_template_id": item.allowed_title_template_ids[0],
            }
            for item in envelope.chart_plans
        ],
    }
    return ClaimTemplateResponseV3_1.model_validate(payload)


@dataclass
class ClaimTemplateLogicalClientV3_1(ClaimLevelLogicalClientV3):
    template_response_mutator: Callable[[dict[str, Any]], dict[str, Any]] | None = None

    def complete_json(self, *, messages: list[dict[str, Any]]):
        payload = _phase_object(messages, PHASE_V3_1)
        if payload is not None:
            envelope = ClaimTemplatePlanEnvelopeV3_1.model_validate(payload)
            response = mock_claim_template_response_v3_1(envelope).model_dump(mode="json")
            if self.template_response_mutator is not None:
                response = self.template_response_mutator(response)
            return _result(content=json.dumps(response, ensure_ascii=False))
        return super().complete_json(messages=messages)


__all__ = ["ClaimTemplateLogicalClientV3_1", "mock_claim_template_response_v3_1"]
