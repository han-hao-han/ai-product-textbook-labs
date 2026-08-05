"""Project internal tool evidence onto the frozen report-reference boundary.

The native Agent needs full tool payloads while it is deciding whether to call
another business tool.  The terminal report model does not: it may only see
the fields that it can legally copy into ``ReportClaim.evidence``.  This
module performs that one-way, fail-closed projection.
"""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.deepseek_client import DeepSeekClientError
from src.evidence_provenance import PolicyRecord, RequestRecord
from src.fact_schema import FactRecord
from src.report_validation import (
    ReportFactReference,
    ReportPolicyReference,
    ReportRequestReference,
    fact_reference,
    policy_reference,
    request_reference,
)
from src.tool_schemas import TOOL_ARGUMENT_MODELS


FROZEN_TOOL_NAMES = frozenset(TOOL_ARGUMENT_MODELS)
FORBIDDEN_TERMINAL_KEYS = frozenset(
    {
        "analysis_scope",
        "arguments",
        "call_id",
        "fact_layer",
        "fact_type",
        "instruction",
        "result",
        "row_count",
        "schema_version",
        "session_id",
        "source_result_path",
        "source_tool",
        "turn_id",
    }
)
TERMINAL_INSTRUCTION = (
    "Return exactly one JSON object matching the final control-response "
    "schema. Use only the supplied report-reference objects for numbers, "
    "dates, claims and chart requests."
)


class StrictProjectionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ReportAdmissibleToolEvidenceV2_3_1(StrictProjectionModel):
    internal_call_id: str = Field(pattern=r"^CALL-\d{3,}$")
    tool_name: str = Field(min_length=1, max_length=100)
    fact_references: list[ReportFactReference] = Field(min_length=1)
    request_references: list[ReportRequestReference] = Field(
        default_factory=list
    )
    policy_references: list[ReportPolicyReference] = Field(
        default_factory=list
    )

    @model_validator(mode="after")
    def validate_tool_name(self) -> "ReportAdmissibleToolEvidenceV2_3_1":
        if self.tool_name not in FROZEN_TOOL_NAMES:
            raise ValueError("tool_name不属于冻结的七个业务工具")
        return self


class ReportAdmissibleEnvelopeV2_3_1(StrictProjectionModel):
    phase: Literal["report_terminal_admissible_evidence"]
    session_id: str = Field(pattern=r"^SESSION-[A-Za-z0-9_-]+$")
    turn_id: str = Field(pattern=r"^TURN-\d{3,}$")
    tool_evidence: list[ReportAdmissibleToolEvidenceV2_3_1] = Field(
        min_length=1
    )
    instruction: Literal[
        "Return exactly one JSON object matching the final control-response "
        "schema. Use only the supplied report-reference objects for numbers, "
        "dates, claims and chart requests."
    ] = TERMINAL_INSTRUCTION


@dataclass(frozen=True)
class TerminalEvidenceProjectionV2_3_1:
    messages: list[dict[str, Any]]
    projected_tool_message_count: int
    removed_tool_payload_keys: tuple[str, ...]
    dropped_assistant_tool_call_messages: int
    terminal_evidence_envelope_added: bool
    source_evidence_bytes: int
    projected_evidence_bytes: int


def _project_call(
    payload: dict[str, Any],
) -> tuple[ReportAdmissibleToolEvidenceV2_3_1, str, str]:
    required = {
        "internal_call_id",
        "tool_name",
        "facts",
        "request_records",
        "policy_records",
    }
    if not required.issubset(payload):
        raise DeepSeekClientError(
            "V2.3.1 terminal tool payload lacks evidence fields"
        )
    call_id = payload["internal_call_id"]
    tool_name = payload["tool_name"]
    if not isinstance(call_id, str) or not isinstance(tool_name, str):
        raise DeepSeekClientError(
            "V2.3.1 call and tool identifiers must be strings"
        )
    try:
        facts = [FactRecord.model_validate(item) for item in payload["facts"]]
        requests = [
            RequestRecord.model_validate(item)
            for item in payload["request_records"]
        ]
        policies = [
            PolicyRecord.model_validate(item)
            for item in payload["policy_records"]
        ]
    except (TypeError, ValueError) as exc:
        raise DeepSeekClientError(
            "V2.3.1 source evidence failed frozen Schema validation"
        ) from exc
    if not facts:
        raise DeepSeekClientError(
            "V2.3.1 executed business tool must produce at least one FACT"
        )
    session_id = facts[0].session_id
    turn_id = facts[0].turn_id
    if any(
        fact.session_id != session_id
        or fact.turn_id != turn_id
        or fact.call_id != call_id
        or fact.source_tool != tool_name
        for fact in facts
    ):
        raise DeepSeekClientError(
            "V2.3.1 FACT provenance does not match its tool call"
        )
    if any(
        record.session_id != session_id or record.turn_id != turn_id
        for record in requests
    ):
        raise DeepSeekClientError(
            "V2.3.1 REQUEST provenance does not match its tool call"
        )
    try:
        projected = ReportAdmissibleToolEvidenceV2_3_1(
            internal_call_id=call_id,
            tool_name=tool_name,
            fact_references=[fact_reference(item) for item in facts],
            request_references=[request_reference(item) for item in requests],
            policy_references=[policy_reference(item) for item in policies],
        )
    except ValueError as exc:
        raise DeepSeekClientError(
            "V2.3.1 report-admissible evidence projection failed"
        ) from exc
    return projected, session_id, turn_id


def _walk_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(
            key for item in value.values() for key in _walk_keys(item)
        )
    if isinstance(value, list):
        return {key for item in value for key in _walk_keys(item)}
    return set()


def assert_report_admissible_envelope(
    envelope: ReportAdmissibleEnvelopeV2_3_1,
) -> None:
    dumped = envelope.model_dump(mode="json")
    # session_id, turn_id and the static instruction are legitimate envelope
    # control fields.  The leak guard applies to the projected evidence body.
    leaked = _walk_keys(dumped["tool_evidence"]) & FORBIDDEN_TERMINAL_KEYS
    if leaked:
        raise DeepSeekClientError(
            "V2.3.1 terminal evidence leaked internal fields: "
            + ", ".join(sorted(leaked))
        )


def project_terminal_messages(
    messages: list[dict[str, Any]],
) -> TerminalEvidenceProjectionV2_3_1:
    clean_messages: list[dict[str, Any]] = []
    evidence_calls: list[ReportAdmissibleToolEvidenceV2_3_1] = []
    removed: set[str] = set()
    dropped_assistant_calls = 0
    session_id: str | None = None
    turn_id: str | None = None
    source_evidence_bytes = 0
    for message in messages:
        copied = deepcopy(message)
        if copied.get("role") == "assistant" and copied.get("tool_calls"):
            dropped_assistant_calls += 1
            continue
        if copied.get("role") != "tool":
            clean_messages.append(copied)
            continue
        content = copied.get("content")
        if not isinstance(content, str):
            raise DeepSeekClientError(
                "V2.3.1 terminal tool message content must be JSON text"
            )
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as exc:
            raise DeepSeekClientError(
                "V2.3.1 terminal tool message is not valid JSON"
            ) from exc
        if not isinstance(payload, dict):
            raise DeepSeekClientError(
                "V2.3.1 terminal tool payload must be an object"
            )
        source_evidence_bytes += len(content.encode("utf-8"))
        projected, observed_session, observed_turn = _project_call(payload)
        if session_id is None:
            session_id, turn_id = observed_session, observed_turn
        elif (session_id, turn_id) != (observed_session, observed_turn):
            raise DeepSeekClientError(
                "V2.3.1 terminal evidence crosses session or turn"
            )
        removed.update(
            set(payload)
            - {
                "internal_call_id",
                "tool_name",
                "facts",
                "request_records",
                "policy_records",
            }
        )
        evidence_calls.append(projected)

    projected_evidence_bytes = 0
    if evidence_calls:
        envelope = ReportAdmissibleEnvelopeV2_3_1(
            phase="report_terminal_admissible_evidence",
            session_id=session_id,
            turn_id=turn_id,
            tool_evidence=evidence_calls,
        )
        assert_report_admissible_envelope(envelope)
        envelope_text = envelope.model_dump_json()
        projected_evidence_bytes = len(envelope_text.encode("utf-8"))
        clean_messages.append({"role": "user", "content": envelope_text})

    return TerminalEvidenceProjectionV2_3_1(
        messages=clean_messages,
        projected_tool_message_count=len(evidence_calls),
        removed_tool_payload_keys=tuple(sorted(removed)),
        dropped_assistant_tool_call_messages=dropped_assistant_calls,
        terminal_evidence_envelope_added=bool(evidence_calls),
        source_evidence_bytes=source_evidence_bytes,
        projected_evidence_bytes=projected_evidence_bytes,
    )


__all__ = [
    "FORBIDDEN_TERMINAL_KEYS",
    "ReportAdmissibleEnvelopeV2_3_1",
    "ReportAdmissibleToolEvidenceV2_3_1",
    "TerminalEvidenceProjectionV2_3_1",
    "assert_report_admissible_envelope",
    "project_terminal_messages",
]
