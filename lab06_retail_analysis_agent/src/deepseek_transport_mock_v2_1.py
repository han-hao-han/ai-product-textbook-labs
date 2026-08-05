"""Provider-shaped offline transport for the V2.1 DeepSeek candidate."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Protocol

from src.deepseek_client import (
    ChatCompletionResult,
    DEEPSEEK_MODEL,
    DeepSeekClientError,
    HttpResponseData,
)


STANDARD_URL = "https://api.deepseek.com/chat/completions"
BETA_URL = "https://api.deepseek.com/beta/chat/completions"


class LogicalV2_1MockClient(Protocol):
    def complete_json(
        self,
        *,
        messages: list[dict[str, Any]],
    ) -> ChatCompletionResult: ...

    def complete_strict_tools(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ChatCompletionResult: ...


@dataclass(frozen=True)
class TransportRequestAuditV2_1:
    request_index: int
    endpoint_kind: Literal["standard_json", "beta_strict_tool"]
    url: str
    phase: str
    model: str
    thinking_disabled: bool
    temperature: int | float | None
    stream: bool | None
    response_format: dict[str, Any] | None
    tool_names: tuple[str, ...]
    all_tools_strict: bool
    tool_choice: str | None
    message_count: int
    message_roles: tuple[str, ...]
    authorization_header_present: bool
    authorization_scheme: str | None
    saved_header_names: tuple[str, ...]
    timeout_seconds: float


@dataclass
class OfflineDeepSeekTransportV2_1:
    """Validate real request serialization without opening a socket."""

    logical_client: LogicalV2_1MockClient
    requests: list[TransportRequestAuditV2_1] = field(
        default_factory=list
    )

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
                "离线传输收到的请求不是合法UTF-8 JSON"
            ) from exc
        if not isinstance(payload, dict):
            raise DeepSeekClientError("离线传输请求顶层必须是对象")
        messages = payload.get("messages")
        if not isinstance(messages, list) or not messages:
            raise DeepSeekClientError("离线传输请求缺少messages")
        tools = payload.get("tools") or []
        if not isinstance(tools, list):
            raise DeepSeekClientError("离线传输tools必须是数组")
        phase = self._phase(messages)
        authorization = headers.get("Authorization")
        authorization_scheme = (
            authorization.split(" ", 1)[0]
            if isinstance(authorization, str) and authorization
            else None
        )
        tool_names = tuple(
            str(tool.get("function", {}).get("name", ""))
            for tool in tools
        )
        all_tools_strict = bool(tools) and all(
            tool.get("function", {}).get("strict") is True
            for tool in tools
        )
        endpoint_kind: Literal[
            "standard_json",
            "beta_strict_tool",
        ]
        if tools:
            endpoint_kind = "beta_strict_tool"
            self._validate_strict_request(url, payload, tools)
        else:
            endpoint_kind = "standard_json"
            self._validate_json_request(url, payload)
        self.requests.append(
            TransportRequestAuditV2_1(
                request_index=len(self.requests) + 1,
                endpoint_kind=endpoint_kind,
                url=url,
                phase=phase,
                model=str(payload.get("model", "")),
                thinking_disabled=(
                    payload.get("thinking") == {"type": "disabled"}
                ),
                temperature=payload.get("temperature"),
                stream=payload.get("stream"),
                response_format=payload.get("response_format"),
                tool_names=tool_names,
                all_tools_strict=all_tools_strict,
                tool_choice=payload.get("tool_choice"),
                message_count=len(messages),
                message_roles=tuple(
                    str(message.get("role", ""))
                    for message in messages
                    if isinstance(message, dict)
                ),
                authorization_header_present=(
                    isinstance(authorization, str)
                    and authorization.startswith("Bearer ")
                ),
                authorization_scheme=authorization_scheme,
                saved_header_names=tuple(sorted(headers)),
                timeout_seconds=timeout_seconds,
            )
        )
        if tools:
            logical = self.logical_client.complete_strict_tools(
                messages=messages,
                tools=tools,
            )
        else:
            logical = self.logical_client.complete_json(
                messages=messages,
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
    def _phase(messages: list[dict[str, Any]]) -> str:
        last = messages[-1]
        if not isinstance(last, dict):
            raise DeepSeekClientError("离线传输message必须是对象")
        content = last.get("content")
        if not isinstance(content, str):
            raise DeepSeekClientError(
                "离线传输最后一条message必须含字符串content"
            )
        try:
            value = json.loads(content)
        except json.JSONDecodeError as exc:
            raise DeepSeekClientError(
                "离线传输无法识别请求阶段"
            ) from exc
        phase = value.get("phase") if isinstance(value, dict) else None
        if not isinstance(phase, str):
            raise DeepSeekClientError("离线传输请求缺少phase")
        return phase

    @staticmethod
    def _validate_common(payload: dict[str, Any]) -> None:
        if payload.get("model") != DEEPSEEK_MODEL:
            raise DeepSeekClientError("离线传输模型名不符合V2.1候选")
        if payload.get("thinking") != {"type": "disabled"}:
            raise DeepSeekClientError("离线传输必须关闭thinking")
        if payload.get("temperature") != 0:
            raise DeepSeekClientError("离线传输temperature必须为0")
        if payload.get("stream") is not False:
            raise DeepSeekClientError("离线传输必须关闭stream")

    @classmethod
    def _validate_json_request(
        cls,
        url: str,
        payload: dict[str, Any],
    ) -> None:
        cls._validate_common(payload)
        if url != STANDARD_URL:
            raise DeepSeekClientError("JSON阶段必须使用标准端点")
        if payload.get("response_format") != {
            "type": "json_object"
        }:
            raise DeepSeekClientError(
                "JSON阶段必须启用json_object响应格式"
            )
        if "tools" in payload or "tool_choice" in payload:
            raise DeepSeekClientError("JSON阶段不得发送工具")

    @classmethod
    def _validate_strict_request(
        cls,
        url: str,
        payload: dict[str, Any],
        tools: list[dict[str, Any]],
    ) -> None:
        cls._validate_common(payload)
        if url != BETA_URL:
            raise DeepSeekClientError("strict工具阶段必须使用Beta端点")
        if len(tools) != 1:
            raise DeepSeekClientError(
                "V2.1每个strict步骤只能暴露一个工具"
            )
        function = tools[0].get("function", {})
        if function.get("strict") is not True:
            raise DeepSeekClientError("工具必须设置strict=true")
        parameters = function.get("parameters")
        if (
            not isinstance(parameters, dict)
            or parameters.get("additionalProperties") is not False
        ):
            raise DeepSeekClientError("strict工具参数必须关闭额外字段")
        if payload.get("tool_choice") != "auto":
            raise DeepSeekClientError("strict工具阶段必须使用auto选择")
        if "response_format" in payload:
            raise DeepSeekClientError(
                "strict工具阶段不得发送response_format"
            )

    @staticmethod
    def _provider_payload(
        logical: ChatCompletionResult,
    ) -> dict[str, Any]:
        tool_calls = [
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
        ]
        return {
            "id": "offline-transport-response",
            "object": "chat.completion",
            "model": DEEPSEEK_MODEL,
            "choices": [
                {
                    "index": 0,
                    "finish_reason": logical.finish_reason,
                    "message": {
                        "role": "assistant",
                        "content": logical.content,
                        "tool_calls": tool_calls,
                    },
                }
            ],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
        }

    def audit_payload(self) -> dict[str, Any]:
        return {
            "schema_version": "1.5.6-h3-v2.1-transport-audit-v1",
            "execution_mode": "offline_injected_transport",
            "real_network_opened": False,
            "real_model_called": False,
            "authorization_value_saved": False,
            "request_body_saved": False,
            "requests": [
                {
                    **asdict(request),
                    "tool_names": list(request.tool_names),
                    "message_roles": list(request.message_roles),
                    "saved_header_names": list(
                        request.saved_header_names
                    ),
                }
                for request in self.requests
            ],
        }
