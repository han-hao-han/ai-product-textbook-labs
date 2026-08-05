"""V2.3 provider transport boundary for no-tool JSON terminals.

Business-tool turns remain unchanged on DeepSeek strict-tools Beta.  Once
the deterministic native agent closes tool permission, this adapter removes
the seven schemas and ``tool_choice`` from the wire request and sends the
same message history to the standard JSON endpoint.
"""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import Any

from src.deepseek_client import (
    DEEPSEEK_MODEL,
    DeepSeekClientError,
    HttpResponseData,
    HttpTransport,
)
from src.tool_schemas import TOOL_ARGUMENT_MODELS


BETA_URL = "https://api.deepseek.com/beta/chat/completions"
STANDARD_URL = "https://api.deepseek.com/chat/completions"
FROZEN_TOOL_NAMES = tuple(TOOL_ARGUMENT_MODELS)
JSON_OBJECT_FORMAT = {"type": "json_object"}


@dataclass(frozen=True)
class TerminalTransportAuditV2_3:
    request_index: int
    phase: str
    inbound_url: str
    outbound_url: str
    inbound_tool_count: int
    outbound_tool_count: int
    inbound_tool_choice: str | None
    outbound_tool_choice_present: bool
    response_format: dict[str, Any] | None
    max_tokens: int
    tool_result_message_count: int
    projected_tool_message_count: int
    removed_tool_payload_keys: tuple[str, ...]
    dropped_assistant_tool_call_messages: int
    outbound_tool_role_message_count: int
    terminal_evidence_envelope_added: bool
    rewritten: bool


@dataclass
class DeepSeekReportTerminalTransportV2_3:
    """Rewrite only the exact closed-tool JSON terminal request."""

    delegate: HttpTransport
    requests: list[TerminalTransportAuditV2_3] = field(default_factory=list)

    def __call__(
        self,
        url: str,
        body: bytes,
        headers: dict[str, str],
        timeout_seconds: float,
    ) -> HttpResponseData:
        try:
            payload = json.loads(body.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DeepSeekClientError(
                "V2.3 transport received invalid UTF-8 JSON"
            ) from exc
        if not isinstance(payload, dict):
            raise DeepSeekClientError("V2.3 request must be a JSON object")

        self._validate_common(payload)
        tools = payload.get("tools")
        if not isinstance(tools, list):
            raise DeepSeekClientError(
                "V2.3 inbound native request must include tools"
            )
        tool_names = tuple(
            str(item.get("function", {}).get("name", ""))
            for item in tools
        )
        if len(tool_names) != 7 or set(tool_names) != set(FROZEN_TOOL_NAMES):
            raise DeepSeekClientError(
                "V2.3 inbound request must contain the frozen seven tools"
            )

        messages = payload.get("messages")
        if not isinstance(messages, list) or not messages:
            raise DeepSeekClientError("V2.3 request must contain messages")
        tool_result_count = sum(
            isinstance(item, dict) and item.get("role") == "tool"
            for item in messages
        )
        terminal = (
            payload.get("tool_choice") == "none"
            and payload.get("response_format") == JSON_OBJECT_FORMAT
        )
        outbound = deepcopy(payload)
        outbound_url = url
        projected_tool_message_count = 0
        removed_tool_payload_keys: tuple[str, ...] = ()
        dropped_assistant_tool_call_messages = 0
        terminal_evidence_envelope_added = False
        if terminal:
            if url != BETA_URL:
                raise DeepSeekClientError(
                    "V2.3 terminal rewrite requires the Beta inbound endpoint"
                )
            expected_max_tokens = 8192 if tool_result_count else 4096
            if payload.get("max_tokens") != expected_max_tokens:
                raise DeepSeekClientError(
                    "V2.3 terminal max_tokens violates stage policy"
                )
            outbound.pop("tools", None)
            outbound.pop("tool_choice", None)
            (
                outbound["messages"],
                projected_tool_message_count,
                removed_tool_payload_keys,
                dropped_assistant_tool_call_messages,
                terminal_evidence_envelope_added,
            ) = self._project_terminal_messages(messages)
            outbound_url = STANDARD_URL
            phase = "standard_json_no_tools_terminal"
        else:
            if url != BETA_URL or payload.get("tool_choice") != "auto":
                raise DeepSeekClientError(
                    "V2.3 business-tool request must remain Beta auto"
                )
            if "response_format" in payload:
                raise DeepSeekClientError(
                    "V2.3 business-tool request must not use JSON mode"
                )
            phase = "beta_strict_business_tools"

        self.requests.append(
            TerminalTransportAuditV2_3(
                request_index=len(self.requests) + 1,
                phase=phase,
                inbound_url=url,
                outbound_url=outbound_url,
                inbound_tool_count=len(tools),
                outbound_tool_count=len(outbound.get("tools") or []),
                inbound_tool_choice=(
                    str(payload.get("tool_choice"))
                    if payload.get("tool_choice") is not None
                    else None
                ),
                outbound_tool_choice_present="tool_choice" in outbound,
                response_format=outbound.get("response_format"),
                max_tokens=int(outbound.get("max_tokens", 0)),
                tool_result_message_count=tool_result_count,
                projected_tool_message_count=projected_tool_message_count,
                removed_tool_payload_keys=removed_tool_payload_keys,
                dropped_assistant_tool_call_messages=(
                    dropped_assistant_tool_call_messages
                ),
                outbound_tool_role_message_count=sum(
                    isinstance(item, dict) and item.get("role") == "tool"
                    for item in outbound["messages"]
                ),
                terminal_evidence_envelope_added=(
                    terminal_evidence_envelope_added
                ),
                rewritten=terminal,
            )
        )
        return self.delegate(
            outbound_url,
            json.dumps(
                outbound,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8"),
            headers,
            timeout_seconds,
        )

    @staticmethod
    def _validate_common(payload: dict[str, Any]) -> None:
        if payload.get("model") != DEEPSEEK_MODEL:
            raise DeepSeekClientError("V2.3 model drifted")
        if payload.get("thinking") != {"type": "disabled"}:
            raise DeepSeekClientError("V2.3 requires thinking disabled")
        if payload.get("temperature") != 0:
            raise DeepSeekClientError("V2.3 requires temperature zero")
        if payload.get("stream") is not False:
            raise DeepSeekClientError("V2.3 requires non-streaming responses")

    @staticmethod
    def _project_terminal_messages(
        messages: list[dict[str, Any]],
    ) -> tuple[
        list[dict[str, Any]],
        int,
        tuple[str, ...],
        int,
        bool,
    ]:
        allowed = {
            "internal_call_id",
            "tool_name",
            "facts",
            "request_records",
            "policy_records",
            "instruction",
        }
        clean_messages: list[dict[str, Any]] = []
        evidence_calls: list[dict[str, Any]] = []
        count = 0
        removed: set[str] = set()
        dropped_assistant_calls = 0
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
                    "V2.3 terminal tool message content must be JSON text"
                )
            try:
                payload = json.loads(content)
            except json.JSONDecodeError as exc:
                raise DeepSeekClientError(
                    "V2.3 terminal tool message is not valid JSON"
                ) from exc
            if not isinstance(payload, dict):
                raise DeepSeekClientError(
                    "V2.3 terminal tool payload must be an object"
                )
            required = {
                "internal_call_id",
                "tool_name",
                "facts",
                "request_records",
                "policy_records",
            }
            if not required.issubset(payload):
                raise DeepSeekClientError(
                    "V2.3 terminal tool payload lacks evidence fields"
                )
            removed.update(set(payload) - allowed)
            evidence_calls.append(
                {key: payload[key] for key in payload if key in allowed}
            )
            count += 1
        if evidence_calls:
            clean_messages.append(
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "phase": "report_terminal_evidence",
                            "tool_evidence": evidence_calls,
                            "instruction": (
                                "Return exactly one JSON object matching the "
                                "final control-response schema. Use only the "
                                "FACT, REQUEST and POLICY evidence above for "
                                "numbers, dates, claims and chart requests."
                            ),
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                }
            )
        return (
            clean_messages,
            count,
            tuple(sorted(removed)),
            dropped_assistant_calls,
            bool(evidence_calls),
        )

    def audit_payload(self) -> dict[str, Any]:
        return {
            "schema_version": (
                "1.5.6-h3-deepseek-report-terminal-transport-v2.3-audit-v1"
            ),
            "request_count": len(self.requests),
            "request_body_saved": False,
            "request_headers_saved": False,
            "authorization_header_value_saved": False,
            "requests": [asdict(item) for item in self.requests],
        }
