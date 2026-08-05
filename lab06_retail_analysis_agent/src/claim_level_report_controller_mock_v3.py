"""Offline model double for the V3 claim-level report controller."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from src.claim_level_report_controller_v3 import (
    CLAIM_PLAN_PHASE,
    CLAIM_RESPONSE_PHASE,
    ClaimPlanEnvelopeV3,
    ClaimStatementResponseV3,
)
from src.deepseek_internal_call_isolation_transport_mock_v2_3_4_2 import (
    CallIsolatedLogicalClientV2_3_4_2,
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


def mock_claim_statement_response_v3(
    envelope: ClaimPlanEnvelopeV3,
) -> ClaimStatementResponseV3:
    statements: list[dict[str, str]] = []
    for item in envelope.claims:
        if item.required_literals:
            statement = "；".join(item.required_literals) + "。"
        elif item.slot_id == "SLOT-003":
            statement = "本节说明结果由确定性工具计算，报告与图表共享同一份工具数据。"
        elif item.slot_id == "SLOT-004":
            statement = "该结果仅是历史数据描述，不构成因果解释或未来预测。"
        elif item.slot_id == "SLOT-005":
            statement = "建议由人工结合业务背景复核，再决定后续行动。"
        elif item.slot_id == "SLOT-006":
            statement = "结论仅限于当前可用的历史数据。"
        else:
            statement = "当前证据没有提供可进一步量化的内容。"
        statements.append({"claim_id": item.claim_id, "statement": statement})
    payload = {
        "phase": CLAIM_RESPONSE_PHASE,
        "session_id": envelope.session_id,
        "turn_id": envelope.turn_id,
        "title": "受控证据经营分析报告",
        "claims": statements,
        "chart_titles": [
            {
                "chart_plan_id": item.chart_plan_id,
                "title": f"{item.tool_name} 确定性工具图表",
            }
            for item in envelope.chart_plans
        ],
    }
    return ClaimStatementResponseV3.model_validate(payload)


@dataclass
class ClaimLevelLogicalClientV3(CallIsolatedLogicalClientV2_3_4_2):
    claim_mutator: Callable[[dict[str, Any]], dict[str, Any]] | None = None

    def complete_json(self, *, messages: list[dict[str, Any]]):
        payload = _phase_object(messages, CLAIM_PLAN_PHASE)
        if payload is not None:
            envelope = ClaimPlanEnvelopeV3.model_validate(payload)
            response = mock_claim_statement_response_v3(envelope).model_dump(mode="json")
            if self.claim_mutator is not None:
                response = self.claim_mutator(response)
            return _result(content=json.dumps(response, ensure_ascii=False))
        return super().complete_json(messages=messages)


__all__ = ["ClaimLevelLogicalClientV3", "mock_claim_statement_response_v3"]
