"""Minimal, auditable DeepSeek native tool-calling validation."""

from __future__ import annotations

import http.client
import json
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlsplit


class ModelValidationError(RuntimeError):
    """Raised when transport or response validation fails."""


@dataclass(frozen=True)
class HttpResponseData:
    status_code: int
    content: bytes


HttpTransport = Callable[
    [str, bytes, dict[str, str], float],
    HttpResponseData,
]


SYSTEM_PROMPT = """
你是“基于真实零售数据的经营分析Agent”的协议验证模型。
你只能选择提供的白名单工具，不能生成或执行Python、SQL或Shell。
所有数值必须由工具计算；本验证阶段不得自行计算经营指标。
每次响应最多提出一个工具调用。
若问题超出工具和数据能力，直接说明缺少的数据与限制，不调用无关工具。
不要输出内部思维过程。
""".strip()


SALES_OVERVIEW_TOOL = {
    "type": "function",
    "function": {
        "name": "get_sales_overview",
        "description": (
            "返回冻结正常销售口径下的销售额、销售数量、订单数和客单价。"
            "不计算利润、预测或库存。"
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "enum": ["all_data", "complete_months_only"],
                    "description": (
                        "all_data表示全部数据并提示不完整期间；"
                        "complete_months_only排除冻结的不完整月份。"
                    ),
                },
                "include_incomplete_period_warning": {
                    "type": "boolean",
                    "description": "是否要求结果包含不完整期间提示。",
                },
            },
            "required": [
                "period",
                "include_incomplete_period_warning",
            ],
            "additionalProperties": False,
        },
    },
}


RANK_PRODUCTS_TOOL = {
    "type": "function",
    "function": {
        "name": "rank_products",
        "description": (
            "按冻结正常销售口径对StockCode进行销售额或销量Top N排名。"
            "不计算利润。"
        ),
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": {
                "metric": {
                    "type": "string",
                    "enum": ["sales_amount", "sales_quantity"],
                },
                "top_n": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10,
                },
                "period": {
                    "type": "string",
                    "enum": ["all_data", "complete_months_only"],
                },
            },
            "required": ["metric", "top_n", "period"],
            "additionalProperties": False,
        },
    },
}


def build_validation_cases() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "MODEL-TOOL-01",
            "purpose": "强制单工具、Beta端点和strict Schema",
            "user_message": (
                "请给出当前固定数据全部正常销售的销售额、销量、"
                "订单数和客单价，并提示不完整期间。"
            ),
            "tools": [SALES_OVERVIEW_TOOL],
            "tool_choice": {
                "type": "function",
                "function": {"name": "get_sales_overview"},
            },
            "expected": {
                "tool_name": "get_sales_overview",
                "period": "all_data",
                "include_incomplete_period_warning": True,
            },
        },
        {
            "case_id": "MODEL-AUTO-02",
            "purpose": "自动选择销售概览而非商品排名",
            "user_message": (
                "当前固定数据的总体销售额、销售数量、订单数和"
                "客单价分别是多少？请提示数据中的不完整期间。"
            ),
            "tools": [SALES_OVERVIEW_TOOL, RANK_PRODUCTS_TOOL],
            "tool_choice": "auto",
            "expected": {
                "tool_name": "get_sales_overview",
                "period": "all_data",
                "include_incomplete_period_warning": True,
            },
        },
        {
            "case_id": "MODEL-BOUNDARY-03",
            "purpose": "利润能力边界拒答且不调用工具",
            "user_message": (
                "哪个商品最赚钱？请计算前5名商品的利润和利润率，"
                "并说明原因。"
            ),
            "tools": [SALES_OVERVIEW_TOOL, RANK_PRODUCTS_TOOL],
            "tool_choice": "auto",
            "expected": {
                "tool_name": None,
                "boundary": "profit_not_supported",
            },
        },
    ]


def build_request(
    case: dict[str, Any],
    *,
    model: str,
) -> dict[str, Any]:
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": case["user_message"]},
        ],
        "tools": case["tools"],
        "tool_choice": case["tool_choice"],
        "thinking": {"type": "disabled"},
        "temperature": 0,
        "max_tokens": 512,
        "stream": False,
    }


def _default_transport(
    url: str,
    body: bytes,
    headers: dict[str, str],
    timeout_seconds: float,
) -> HttpResponseData:
    target = urlsplit(url)
    if target.scheme != "https" or not target.hostname:
        raise ModelValidationError("模型验证只允许HTTPS端点。")
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
    except TimeoutError as error:
        raise ModelValidationError("模型验证请求超时。") from error
    except OSError as error:
        raise ModelValidationError(
            f"模型验证网络失败：{type(error).__name__}"
        ) from error
    finally:
        connection.close()


def _decode_response(content: bytes) -> dict[str, Any]:
    try:
        decoded = content.decode("utf-8", errors="strict")
        payload = json.loads(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ModelValidationError("模型响应不是合法UTF-8 JSON。") from error
    if not isinstance(payload, dict):
        raise ModelValidationError("模型响应顶层必须为JSON对象。")
    return payload


def _extract_message(payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    try:
        choice = payload["choices"][0]
        finish_reason = str(choice["finish_reason"])
        message = choice["message"]
    except (KeyError, IndexError, TypeError) as error:
        raise ModelValidationError("模型响应缺少choice message。") from error
    if not isinstance(message, dict):
        raise ModelValidationError("模型message必须为对象。")
    return finish_reason, message


def _parse_tool_calls(message: dict[str, Any]) -> list[dict[str, Any]]:
    raw_calls = message.get("tool_calls") or []
    if not isinstance(raw_calls, list):
        raise ModelValidationError("tool_calls必须为数组。")
    parsed: list[dict[str, Any]] = []
    for raw_call in raw_calls:
        try:
            function = raw_call["function"]
            arguments = json.loads(function["arguments"])
            parsed.append(
                {
                    "call_id": str(raw_call["id"]),
                    "tool_name": str(function["name"]),
                    "arguments": arguments,
                }
            )
        except (
            KeyError,
            TypeError,
            json.JSONDecodeError,
        ) as error:
            raise ModelValidationError(
                "工具调用缺少名称、ID或合法JSON参数。"
            ) from error
    return parsed


def evaluate_case(
    case: dict[str, Any],
    *,
    finish_reason: str,
    message: dict[str, Any],
) -> dict[str, Any]:
    tool_calls = _parse_tool_calls(message)
    expected = case["expected"]
    issues: list[str] = []
    if len(tool_calls) > 1:
        issues.append("同一响应返回多个工具调用")

    expected_tool = expected["tool_name"]
    if expected_tool is None:
        if tool_calls:
            issues.append("能力边界题不应调用工具")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            issues.append("能力边界题缺少文字说明")
        limitation_terms = ("利润", "成本", "无法", "不能", "缺少", "不支持")
        if isinstance(content, str) and not any(
            term in content for term in limitation_terms
        ):
            issues.append("能力边界回答未出现明确限制用语")
    else:
        if len(tool_calls) != 1:
            issues.append("应返回且仅返回一个工具调用")
        elif tool_calls[0]["tool_name"] != expected_tool:
            issues.append(
                f"工具选择错误：{tool_calls[0]['tool_name']}"
            )
        else:
            arguments = tool_calls[0]["arguments"]
            for key, expected_value in expected.items():
                if key == "tool_name":
                    continue
                if arguments.get(key) != expected_value:
                    issues.append(
                        f"参数{key}不符合预期：{arguments.get(key)!r}"
                    )
        if finish_reason != "tool_calls":
            issues.append(f"工具调用finish_reason异常：{finish_reason}")

    return {
        "case_id": case["case_id"],
        "passed": not issues,
        "issues": issues,
        "finish_reason": finish_reason,
        "tool_calls": tool_calls,
        "assistant_content": message.get("content"),
    }


def call_validation_case(
    case: dict[str, Any],
    *,
    api_key: str,
    base_url: str,
    model: str,
    timeout_seconds: float = 120,
    transport: HttpTransport = _default_transport,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not api_key.strip():
        raise ValueError("API Key不能为空。")
    request = build_request(case, model=model)
    request_bytes = json.dumps(
        request,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    endpoint = f"{base_url.rstrip('/')}/chat/completions"
    started = time.perf_counter()
    response = transport(
        endpoint,
        request_bytes,
        {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
        },
        timeout_seconds,
    )
    elapsed = round(time.perf_counter() - started, 6)
    payload = _decode_response(response.content)
    if not 200 <= response.status_code < 300:
        error = payload.get("error")
        message = (
            error.get("message")
            if isinstance(error, dict)
            else "模型验证返回HTTP错误"
        )
        raise ModelValidationError(
            f"HTTP {response.status_code}: {message}"
        )
    finish_reason, message = _extract_message(payload)
    evaluation = evaluate_case(
        case,
        finish_reason=finish_reason,
        message=message,
    )
    raw_record = {
        "schema_version": "1.5.6-model-protocol-raw-v1",
        "case_id": case["case_id"],
        "purpose": case["purpose"],
        "provider": "DeepSeek",
        "base_url": base_url,
        "requested_model": model,
        "response_id": payload.get("id"),
        "response_model": payload.get("model"),
        "system_fingerprint": payload.get("system_fingerprint"),
        "usage": payload.get("usage"),
        "elapsed_seconds": elapsed,
        "http_status": response.status_code,
        "raw_response": payload,
        "api_key_saved": False,
        "authorization_header_saved": False,
    }
    return raw_record, evaluation
