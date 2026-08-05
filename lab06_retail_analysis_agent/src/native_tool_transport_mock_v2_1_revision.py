"""Injected HTTP transport for the corrected native-tool online candidate."""

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
from src.native_tool_agent_v2_1_revision import (
    FIXED_TOOL_SEQUENCES,
    FROZEN_TOOL_NAMES,
)
from src.fixed_question_validation import load_frozen_questions


BETA_URL = "https://api.deepseek.com/beta/chat/completions"


@dataclass(frozen=True)
class NativeTransportRequestAudit:
    request_index: int
    url: str
    model: str
    tool_names: tuple[str, ...]
    tool_count: int
    all_tools_strict: bool
    all_parameters_closed: bool
    tool_choice: str | None
    thinking_disabled: bool
    temperature: int | float | None
    stream: bool | None
    response_format_present: bool
    response_format: dict[str, Any] | None
    message_count: int
    message_roles: tuple[str, ...]
    tool_result_message_count: int
    authorization_header_present: bool
    authorization_scheme: str | None
    timeout_seconds: float
    max_tokens: int


@dataclass
class OfflineNativeToolTransportV2_1Revision:
    """Validate serialized requests and return provider-shaped responses."""

    logical_client: Any
    expected_model: str = DEEPSEEK_MODEL
    q06_terminal_policy_enabled: bool = True
    q06_terminal_json_policy_enabled: bool = True
    terminal_question_ids: tuple[str, ...] | None = None
    terminal_json_question_ids: tuple[str, ...] | None = None
    requests: list[NativeTransportRequestAudit] = field(default_factory=list)

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
                "offline native request is not valid UTF-8 JSON"
            ) from exc
        if not isinstance(payload, dict):
            raise DeepSeekClientError("offline native request must be an object")
        messages = payload.get("messages")
        tools = payload.get("tools")
        if not isinstance(messages, list) or not messages:
            raise DeepSeekClientError("offline native request lacks messages")
        if not isinstance(tools, list):
            raise DeepSeekClientError("offline native request lacks tools")

        tool_names = tuple(
            str(item.get("function", {}).get("name", ""))
            for item in tools
        )
        all_tools_strict = all(
            item.get("function", {}).get("strict") is True
            for item in tools
        )
        all_parameters_closed = all(
            item.get("function", {})
            .get("parameters", {})
            .get("additionalProperties")
            is False
            for item in tools
        )
        self._validate_request(
            url=url,
            payload=payload,
            messages=messages,
            tool_names=tool_names,
            all_tools_strict=all_tools_strict,
            all_parameters_closed=all_parameters_closed,
        )

        authorization = headers.get("Authorization")
        self.requests.append(
            NativeTransportRequestAudit(
                request_index=len(self.requests) + 1,
                url=url,
                model=str(payload.get("model", "")),
                tool_names=tool_names,
                tool_count=len(tools),
                all_tools_strict=all_tools_strict,
                all_parameters_closed=all_parameters_closed,
                tool_choice=payload.get("tool_choice"),
                thinking_disabled=(
                    payload.get("thinking") == {"type": "disabled"}
                ),
                temperature=payload.get("temperature"),
                stream=payload.get("stream"),
                response_format_present="response_format" in payload,
                response_format=payload.get("response_format"),
                message_count=len(messages),
                message_roles=tuple(
                    str(item.get("role", ""))
                    for item in messages
                    if isinstance(item, dict)
                ),
                tool_result_message_count=sum(
                    isinstance(item, dict) and item.get("role") == "tool"
                    for item in messages
                ),
                authorization_header_present=(
                    isinstance(authorization, str)
                    and authorization.startswith("Bearer ")
                ),
                authorization_scheme=(
                    authorization.split(" ", 1)[0]
                    if isinstance(authorization, str) and authorization
                    else None
                ),
                timeout_seconds=timeout_seconds,
                max_tokens=int(payload.get("max_tokens", 0)),
            )
        )
        logical = self.logical_client.complete_strict_tools(
            messages=messages,
            tools=tools,
            tool_choice=str(payload.get("tool_choice")),
        )
        return HttpResponseData(
            status_code=200,
            content=json.dumps(
                self._provider_payload(logical),
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8"),
        )

    def _validate_request(
        self,
        *,
        url: str,
        payload: dict[str, Any],
        messages: list[dict[str, Any]],
        tool_names: tuple[str, ...],
        all_tools_strict: bool,
        all_parameters_closed: bool,
    ) -> None:
        if url != BETA_URL:
            raise DeepSeekClientError("native tools must use the Beta endpoint")
        if payload.get("model") != self.expected_model:
            raise DeepSeekClientError("unexpected native candidate model")
        if len(tool_names) != 7 or set(tool_names) != set(FROZEN_TOOL_NAMES):
            raise DeepSeekClientError(
                "every native request must expose all seven frozen tools"
            )
        if not all_tools_strict or not all_parameters_closed:
            raise DeepSeekClientError("all native tools must be strict and closed")
        first_user = next(
            (
                item.get("content")
                for item in messages
                if isinstance(item, dict) and item.get("role") == "user"
            ),
            None,
        )
        question_by_text = {
            item["question"]: question_id
            for question_id, item in load_frozen_questions().items()
        }
        question_id = question_by_text.get(first_user)
        tool_result_count = sum(
            isinstance(item, dict) and item.get("role") == "tool"
            for item in messages
        )
        lock_ids = (
            set(self.terminal_question_ids)
            if self.terminal_question_ids is not None
            else ({"Q06"} if self.q06_terminal_policy_enabled else set())
        )
        terminal = (
            question_id in lock_ids
            and tool_result_count == len(FIXED_TOOL_SEQUENCES[question_id])
        )
        expected_tool_choice = "none" if terminal else "auto"
        if payload.get("tool_choice") != expected_tool_choice:
            raise DeepSeekClientError(
                "native candidate tool_choice violates terminal policy"
            )
        if payload.get("thinking") != {"type": "disabled"}:
            raise DeepSeekClientError("native candidate must disable thinking")
        if payload.get("temperature") != 0:
            raise DeepSeekClientError("native candidate temperature must be zero")
        if payload.get("stream") is not False:
            raise DeepSeekClientError("native candidate must disable streaming")
        json_ids = (
            set(self.terminal_json_question_ids)
            if self.terminal_json_question_ids is not None
            else (
                {"Q06"}
                if self.q06_terminal_json_policy_enabled
                else set()
            )
        )
        terminal_json_expected = (
            question_id in json_ids and expected_tool_choice == "none"
        )
        expected_max_tokens = (
            8192
            if terminal_json_expected and tool_result_count > 0
            else 4096
        )
        if payload.get("max_tokens") != expected_max_tokens:
            raise DeepSeekClientError(
                "native candidate max_tokens violates response-stage policy"
            )
        if terminal_json_expected:
            if payload.get("response_format") != {
                "type": "json_object"
            }:
                raise DeepSeekClientError(
                    "terminal request must use JSON response_format"
                )
        elif "response_format" in payload:
            raise DeepSeekClientError(
                "non-terminal native requests must not use response_format"
            )

    def _provider_payload(self, logical: ChatCompletionResult) -> dict[str, Any]:
        return {
            "id": "offline-native-transport-response",
            "object": "chat.completion",
            "model": self.expected_model,
            "usage": logical.usage
            or {
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "total_tokens": 120,
            },
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
        }

    def audit_payload(self) -> dict[str, Any]:
        return {
            "schema_version": (
                "1.5.6-h3-native-tool-offline-transport-audit-v1"
            ),
            "execution_mode": "offline_injected_transport",
            "real_network_opened": False,
            "real_model_called": False,
            "api_key_read_from_environment": False,
            "authorization_value_saved": False,
            "request_body_saved": False,
            "requests": [
                {
                    **asdict(request),
                    "tool_names": list(request.tool_names),
                    "message_roles": list(request.message_roles),
                }
                for request in self.requests
            ],
        }
