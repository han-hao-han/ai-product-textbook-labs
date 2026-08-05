"""Minimal DeepSeek Chat Completions client with injectable transport."""

from __future__ import annotations

import http.client
import json
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import urlsplit


DEEPSEEK_STANDARD_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_STRICT_TOOL_BASE_URL = "https://api.deepseek.com/beta"
DEEPSEEK_BASE_URL = DEEPSEEK_STANDARD_BASE_URL
DEEPSEEK_MODEL = "deepseek-v4-flash"
DEEPSEEK_ENDPOINT = "/chat/completions"
DEFAULT_MAX_TOKENS = 4096
REPORT_TERMINAL_MAX_TOKENS = 8192
PROVIDER_DOCUMENTED_MAX_OUTPUT_TOKENS = 384000


class DeepSeekClientError(RuntimeError):
    """Raised when transport or provider response validation fails."""


class TerminalOutputTruncatedError(DeepSeekClientError):
    """Raised before parsing when the provider exhausted output capacity."""


@dataclass(frozen=True)
class HttpResponseData:
    status_code: int
    content: bytes


HttpTransport = Callable[
    [str, bytes, dict[str, str], float],
    HttpResponseData,
]
ResponseEventSink = Callable[[str, dict[str, Any]], None]


@dataclass(frozen=True)
class ProviderToolCall:
    provider_call_id: str
    tool_name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ChatCompletionResult:
    finish_reason: str
    content: str | None
    tool_calls: tuple[ProviderToolCall, ...]
    raw_response: dict[str, Any]
    usage: dict[str, Any] | None


def strict_tool_request_max_tokens(
    *,
    messages: list[dict[str, Any]],
    tool_choice: str,
    response_format: dict[str, str] | None,
) -> int:
    """Select the frozen bounded capacity from deterministic request state."""
    report_terminal = (
        tool_choice == "none"
        and response_format == {"type": "json_object"}
        and any(message.get("role") == "tool" for message in messages)
    )
    return (
        REPORT_TERMINAL_MAX_TOKENS
        if report_terminal
        else DEFAULT_MAX_TOKENS
    )


def provider_output_was_truncated(
    raw_responses: tuple[dict[str, Any], ...] | list[dict[str, Any]],
) -> bool:
    """Return true only for an explicitly saved provider length finish."""
    if not raw_responses:
        return False
    try:
        return raw_responses[-1]["choices"][0]["finish_reason"] == "length"
    except (KeyError, IndexError, TypeError):
        return False


def _default_transport(
    url: str,
    body: bytes,
    headers: dict[str, str],
    timeout_seconds: float,
) -> HttpResponseData:
    target = urlsplit(url)
    if target.scheme != "https" or not target.hostname:
        raise DeepSeekClientError("模型请求只允许HTTPS端点")
    path = target.path or "/"
    if target.query:
        path = f"{path}?{target.query}"
    connection = http.client.HTTPSConnection(
        target.hostname,
        target.port or 443,
        timeout=timeout_seconds,
    )
    try:
        connection.request("POST", path, body=body, headers=headers)
        response = connection.getresponse()
        return HttpResponseData(
            status_code=response.status,
            content=response.read(),
        )
    except TimeoutError as exc:
        raise DeepSeekClientError("模型请求超时") from exc
    except OSError as exc:
        raise DeepSeekClientError(
            f"模型网络请求失败：{type(exc).__name__}"
        ) from exc
    finally:
        connection.close()


def _decode_payload(content: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(content.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DeepSeekClientError("模型响应不是合法UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise DeepSeekClientError("模型响应顶层必须是JSON对象")
    return payload


def _parse_tool_calls(message: dict[str, Any]) -> tuple[ProviderToolCall, ...]:
    raw_calls = message.get("tool_calls") or []
    if not isinstance(raw_calls, list):
        raise DeepSeekClientError("模型tool_calls必须是数组")
    parsed: list[ProviderToolCall] = []
    for raw_call in raw_calls:
        try:
            function = raw_call["function"]
            arguments = json.loads(function["arguments"])
            if not isinstance(arguments, dict):
                raise TypeError("arguments must be an object")
            parsed.append(
                ProviderToolCall(
                    provider_call_id=str(raw_call["id"]),
                    tool_name=str(function["name"]),
                    arguments=arguments,
                )
            )
        except (
            KeyError,
            TypeError,
            json.JSONDecodeError,
        ) as exc:
            raise DeepSeekClientError(
                "工具调用缺少ID、名称或合法JSON对象参数"
            ) from exc
    return tuple(parsed)


@dataclass
class DeepSeekChatClient:
    api_key: str = field(repr=False)
    base_url: str = DEEPSEEK_BASE_URL
    model: str = DEEPSEEK_MODEL
    timeout_seconds: float = 120.0
    transport: HttpTransport = field(
        default=_default_transport,
        repr=False,
    )
    response_event_sink: ResponseEventSink | None = field(
        default=None,
        repr=False,
    )

    def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ChatCompletionResult:
        return self._complete_request(
            messages=messages,
            tools=tools,
            base_url=self.base_url,
            response_format=None,
        )

    def complete_json(
        self,
        *,
        messages: list[dict[str, Any]],
    ) -> ChatCompletionResult:
        """Use the standard endpoint's JSON Output mode without tools."""
        return self._complete_request(
            messages=messages,
            tools=[],
            base_url=DEEPSEEK_STANDARD_BASE_URL,
            response_format={"type": "json_object"},
        )

    def complete_strict_tools(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: str = "auto",
        response_format: dict[str, str] | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> ChatCompletionResult:
        """Use the Beta endpoint required for server-side strict tools."""
        if not tools:
            raise DeepSeekClientError("strict工具阶段必须提供工具Schema")
        if any(
            tool.get("function", {}).get("strict") is not True
            for tool in tools
        ):
            raise DeepSeekClientError(
                "strict工具阶段的所有function都必须设置strict=true"
            )
        if tool_choice not in {"auto", "none"}:
            raise DeepSeekClientError(
                "strict工具阶段tool_choice只允许auto或none"
            )
        if response_format is not None:
            if tool_choice != "none":
                raise DeepSeekClientError(
                    "strict工具JSON终态只允许tool_choice=none"
                )
            if response_format != {"type": "json_object"}:
                raise DeepSeekClientError(
                    "strict工具JSON终态只允许json_object"
                )
        if (
            isinstance(max_tokens, bool)
            or not isinstance(max_tokens, int)
            or not 1 <= max_tokens <= PROVIDER_DOCUMENTED_MAX_OUTPUT_TOKENS
        ):
            raise DeepSeekClientError("max_tokens超出受控范围")
        return self._complete_request(
            messages=messages,
            tools=tools,
            base_url=DEEPSEEK_STRICT_TOOL_BASE_URL,
            response_format=response_format,
            tool_choice=tool_choice,
            max_tokens=max_tokens,
        )

    def _complete_request(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        base_url: str,
        response_format: dict[str, str] | None,
        tool_choice: str | None = None,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> ChatCompletionResult:
        if not self.api_key.strip():
            raise DeepSeekClientError("模型API Key为空")
        request_body = {
            "model": self.model,
            "messages": messages,
            "thinking": {"type": "disabled"},
            "temperature": 0,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if tools:
            request_body["tools"] = tools
            request_body["tool_choice"] = tool_choice or "auto"
        if response_format is not None:
            request_body["response_format"] = response_format
        url = f"{base_url.rstrip('/')}{DEEPSEEK_ENDPOINT}"
        response = self.transport(
            url,
            json.dumps(
                request_body,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8"),
            {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            self.timeout_seconds,
        )
        if self.response_event_sink is not None:
            self.response_event_sink(
                "http_response_received",
                {
                    "status_code": response.status_code,
                    "content": response.content,
                },
            )
        payload = _decode_payload(response.content)
        if not 200 <= response.status_code < 300:
            error_type = "provider_error"
            if isinstance(payload.get("error"), dict):
                error_type = str(
                    payload["error"].get("type") or error_type
                )
            raise DeepSeekClientError(
                f"模型服务返回HTTP {response.status_code}：{error_type}"
            )
        try:
            choice = payload["choices"][0]
            finish_reason = str(choice["finish_reason"])
            message = choice["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise DeepSeekClientError(
                "模型响应缺少choice message"
            ) from exc
        if not isinstance(message, dict):
            raise DeepSeekClientError("模型message必须是对象")
        content = message.get("content")
        if content is not None and not isinstance(content, str):
            raise DeepSeekClientError("模型content必须是字符串或null")
        usage = payload.get("usage")
        if usage is not None and not isinstance(usage, dict):
            raise DeepSeekClientError("模型usage必须是对象或null")
        return ChatCompletionResult(
            finish_reason=finish_reason,
            content=content,
            tool_calls=_parse_tool_calls(message),
            raw_response=payload,
            usage=usage,
        )
