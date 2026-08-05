"""Offline provider double for the V2.3 split endpoint protocol."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from src.deepseek_client import (
    ChatCompletionResult,
    DEEPSEEK_MODEL,
    DeepSeekClientError,
    HttpResponseData,
)
from src.deepseek_report_terminal_transport_v2_3 import (
    BETA_URL,
    FROZEN_TOOL_NAMES,
    JSON_OBJECT_FORMAT,
    STANDARD_URL,
)


@dataclass(frozen=True)
class ProviderWireAuditV2_3:
    request_index: int
    endpoint: str
    tool_count: int
    tool_names: tuple[str, ...]
    tool_choice_present: bool
    tool_choice: str | None
    response_format: dict[str, Any] | None
    max_tokens: int
    message_roles: tuple[str, ...]
    tool_payload_keys: tuple[tuple[str, ...], ...]
    terminal_evidence_call_keys: tuple[tuple[str, ...], ...]


@dataclass
class OfflineDeepSeekProviderV2_3:
    logical_client: Any
    requests: list[ProviderWireAuditV2_3] = field(default_factory=list)

    def __call__(
        self,
        url: str,
        body: bytes,
        headers: dict[str, str],
        timeout_seconds: float,
    ) -> HttpResponseData:
        del timeout_seconds
        try:
            payload = json.loads(body.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DeepSeekClientError(
                "V2.3 offline provider received invalid JSON"
            ) from exc
        if not isinstance(payload, dict):
            raise DeepSeekClientError("V2.3 provider payload must be an object")
        if payload.get("model") != DEEPSEEK_MODEL:
            raise DeepSeekClientError("V2.3 provider model drifted")
        if payload.get("thinking") != {"type": "disabled"}:
            raise DeepSeekClientError("V2.3 provider thinking must be disabled")
        if payload.get("temperature") != 0 or payload.get("stream") is not False:
            raise DeepSeekClientError("V2.3 provider sampling drifted")
        messages = payload.get("messages")
        if not isinstance(messages, list) or not messages:
            raise DeepSeekClientError("V2.3 provider requires messages")
        tools = payload.get("tools") or []
        if not isinstance(tools, list):
            raise DeepSeekClientError("V2.3 provider tools must be a list")
        tool_names = tuple(
            str(item.get("function", {}).get("name", ""))
            for item in tools
        )

        if url == BETA_URL:
            if len(tools) != 7 or set(tool_names) != set(FROZEN_TOOL_NAMES):
                raise DeepSeekClientError(
                    "V2.3 Beta request must expose seven tools"
                )
            if payload.get("tool_choice") != "auto":
                raise DeepSeekClientError(
                    "V2.3 Beta request must use tool_choice auto"
                )
            if "response_format" in payload:
                raise DeepSeekClientError(
                    "V2.3 Beta request must not use JSON mode"
                )
            logical = self.logical_client.complete_strict_tools(
                messages=messages,
                tools=tools,
                tool_choice="auto",
                response_format=None,
            )
        elif url == STANDARD_URL:
            if tools or "tools" in payload or "tool_choice" in payload:
                raise DeepSeekClientError(
                    "V2.3 standard terminal must not expose tools"
                )
            if payload.get("response_format") != JSON_OBJECT_FORMAT:
                raise DeepSeekClientError(
                    "V2.3 standard terminal requires json_object"
                )
            logical = self.logical_client.complete_json(messages=messages)
        else:
            raise DeepSeekClientError("V2.3 provider endpoint drifted")

        self.requests.append(
            ProviderWireAuditV2_3(
                request_index=len(self.requests) + 1,
                endpoint=url,
                tool_count=len(tools),
                tool_names=tool_names,
                tool_choice_present="tool_choice" in payload,
                tool_choice=(
                    str(payload.get("tool_choice"))
                    if payload.get("tool_choice") is not None
                    else None
                ),
                response_format=payload.get("response_format"),
                max_tokens=int(payload.get("max_tokens", 0)),
                message_roles=tuple(
                    str(item.get("role", ""))
                    for item in messages
                    if isinstance(item, dict)
                ),
                tool_payload_keys=tuple(
                    tuple(sorted(json.loads(item["content"])))
                    for item in messages
                    if isinstance(item, dict) and item.get("role") == "tool"
                ),
                terminal_evidence_call_keys=self._terminal_evidence_call_keys(
                    messages
                ),
            )
        )
        return HttpResponseData(
            status_code=200,
            content=json.dumps(
                self._provider_payload(logical),
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8"),
        )

    @staticmethod
    def _provider_payload(logical: ChatCompletionResult) -> dict[str, Any]:
        return {
            "id": "offline-v2-3-provider-response",
            "object": "chat.completion",
            "model": DEEPSEEK_MODEL,
            "choices": [
                {
                    "index": 0,
                    "finish_reason": logical.finish_reason,
                    "message": {
                        "role": "assistant",
                        "content": logical.content,
                        "tool_calls": [
                            {
                                "id": call.provider_call_id,
                                "type": "function",
                                "function": {
                                    "name": call.tool_name,
                                    "arguments": json.dumps(
                                        call.arguments,
                                        ensure_ascii=False,
                                        separators=(",", ":"),
                                    ),
                                },
                            }
                            for call in logical.tool_calls
                        ],
                    },
                }
            ],
            "usage": logical.usage
            or {
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "total_tokens": 120,
            },
        }

    def audit_payload(self) -> dict[str, Any]:
        return {
            "schema_version": "1.5.6-h3-v2.3-offline-provider-audit-v1",
            "real_network_opened": False,
            "real_model_called": False,
            "request_headers_saved": False,
            "request_body_saved": False,
            "authorization_header_value_saved": False,
            "requests": [
                {
                    **asdict(item),
                    "tool_names": list(item.tool_names),
                    "message_roles": list(item.message_roles),
                    "tool_payload_keys": [
                        list(keys) for keys in item.tool_payload_keys
                    ],
                    "terminal_evidence_call_keys": [
                        list(keys)
                        for keys in item.terminal_evidence_call_keys
                    ],
                }
                for item in self.requests
            ],
        }

    @staticmethod
    def _terminal_evidence_call_keys(
        messages: list[dict[str, Any]],
    ) -> tuple[tuple[str, ...], ...]:
        for item in reversed(messages):
            if not isinstance(item, dict) or item.get("role") != "user":
                continue
            content = item.get("content")
            if not isinstance(content, str):
                continue
            try:
                payload = json.loads(content)
            except json.JSONDecodeError:
                continue
            if (
                isinstance(payload, dict)
                and payload.get("phase") == "report_terminal_evidence"
            ):
                calls = payload.get("tool_evidence")
                if not isinstance(calls, list):
                    raise DeepSeekClientError(
                        "V2.3 evidence envelope calls must be a list"
                    )
                return tuple(
                    tuple(sorted(call))
                    for call in calls
                    if isinstance(call, dict)
                )
        return ()


@dataclass
class FrozenNativeLogicalClientV2_3:
    """Expose a no-tools JSON method around the frozen logical mock."""

    delegate: Any

    def complete_strict_tools(self, **kwargs: Any) -> ChatCompletionResult:
        return self.delegate.complete_strict_tools(**kwargs)

    def complete_json(
        self,
        *,
        messages: list[dict[str, Any]],
    ) -> ChatCompletionResult:
        expanded_messages: list[dict[str, Any]] = []
        evidence_calls: list[dict[str, Any]] = []
        for message in messages:
            if message.get("role") != "user":
                expanded_messages.append(message)
                continue
            content = message.get("content")
            try:
                payload = json.loads(content) if isinstance(content, str) else None
            except json.JSONDecodeError:
                payload = None
            if (
                isinstance(payload, dict)
                and payload.get("phase") == "report_terminal_evidence"
            ):
                evidence_calls = list(payload.get("tool_evidence") or [])
                continue
            expanded_messages.append(message)
        for index, call in enumerate(evidence_calls, start=1):
            expanded_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": f"offline-v2-3-evidence-{index}",
                    "content": json.dumps(
                        call,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                }
            )
        fake_tools = [
            {"function": {"name": name, "strict": True}}
            for name in FROZEN_TOOL_NAMES
        ]
        return self.delegate.complete_strict_tools(
            messages=expanded_messages,
            tools=fake_tools,
            tool_choice="none",
            response_format=JSON_OBJECT_FORMAT,
        )
