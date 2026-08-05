from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.model_protocol_validation import (  # noqa: E402
    HttpResponseData,
    build_request,
    build_validation_cases,
    call_validation_case,
)


def mock_transport_for(payload: dict):
    def transport(
        url: str,
        body: bytes,
        headers: dict[str, str],
        timeout_seconds: float,
    ) -> HttpResponseData:
        request = json.loads(body)
        if not url.endswith("/chat/completions"):
            raise AssertionError(url)
        if headers.get("Authorization") != "Bearer test-key":
            raise AssertionError("Authorization header missing")
        if request["thinking"] != {"type": "disabled"}:
            raise AssertionError("thinking mode changed")
        if timeout_seconds != 120:
            raise AssertionError("timeout changed")
        return HttpResponseData(
            status_code=200,
            content=json.dumps(payload).encode("utf-8"),
        )

    return transport


class ModelProtocolValidationTests(unittest.TestCase):
    def test_all_function_schemas_are_strict_and_closed(self) -> None:
        for case in build_validation_cases():
            request = build_request(case, model="deepseek-v4-pro")
            for tool in request["tools"]:
                function = tool["function"]
                parameters = function["parameters"]
                self.assertTrue(function["strict"])
                self.assertFalse(parameters["additionalProperties"])
                self.assertEqual(
                    set(parameters["properties"]),
                    set(parameters["required"]),
                )

    def test_single_tool_response_is_parsed_and_passes(self) -> None:
        case = build_validation_cases()[0]
        payload = {
            "id": "response-1",
            "model": "deepseek-v4-pro",
            "system_fingerprint": "fp-test",
            "usage": {"total_tokens": 42},
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call-1",
                                "type": "function",
                                "function": {
                                    "name": "get_sales_overview",
                                    "arguments": json.dumps(
                                        {
                                            "period": "all_data",
                                            "include_incomplete_period_warning": True,
                                        }
                                    ),
                                },
                            }
                        ],
                    },
                }
            ],
        }

        raw, evaluation = call_validation_case(
            case,
            api_key="test-key",
            base_url="https://api.deepseek.com",
            model="deepseek-v4-pro",
            transport=mock_transport_for(payload),
        )

        self.assertTrue(evaluation["passed"])
        self.assertFalse(raw["api_key_saved"])
        self.assertNotIn("test-key", str(raw))

    def test_boundary_response_passes_without_tool_call(self) -> None:
        case = build_validation_cases()[2]
        payload = {
            "id": "response-3",
            "model": "deepseek-v4-pro",
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "role": "assistant",
                        "content": "缺少成本和利润字段，无法计算；可改做销售额排名。",
                    },
                }
            ],
        }

        _, evaluation = call_validation_case(
            case,
            api_key="test-key",
            base_url="https://api.deepseek.com",
            model="deepseek-v4-pro",
            transport=mock_transport_for(payload),
        )

        self.assertTrue(evaluation["passed"])
        self.assertEqual(evaluation["tool_calls"], [])

    def test_multiple_tool_calls_are_rejected(self) -> None:
        case = build_validation_cases()[1]
        repeated_call = {
            "id": "call-x",
            "type": "function",
            "function": {
                "name": "get_sales_overview",
                "arguments": json.dumps(
                    {
                        "period": "all_data",
                        "include_incomplete_period_warning": True,
                    }
                ),
            },
        }
        payload = {
            "id": "response-2",
            "model": "deepseek-v4-pro",
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [repeated_call, repeated_call],
                    },
                }
            ],
        }

        _, evaluation = call_validation_case(
            case,
            api_key="test-key",
            base_url="https://api.deepseek.com",
            model="deepseek-v4-pro",
            transport=mock_transport_for(payload),
        )

        self.assertFalse(evaluation["passed"])
        self.assertIn("同一响应返回多个工具调用", evaluation["issues"])


if __name__ == "__main__":
    unittest.main()
