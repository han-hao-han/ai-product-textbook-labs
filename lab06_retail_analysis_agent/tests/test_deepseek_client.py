from __future__ import annotations

import json
import unittest

from src.deepseek_client import (
    DeepSeekChatClient,
    DeepSeekClientError,
    HttpResponseData,
)


class DeepSeekClientTests(unittest.TestCase):
    def test_builds_frozen_request_without_exposing_key_in_result(self) -> None:
        captured = {}

        def transport(url, body, headers, timeout):
            captured.update(
                {
                    "url": url,
                    "body": json.loads(body),
                    "headers": headers,
                    "timeout": timeout,
                }
            )
            return HttpResponseData(
                200,
                json.dumps(
                    {
                        "choices": [
                            {
                                "finish_reason": "tool_calls",
                                "message": {
                                    "content": None,
                                    "tool_calls": [
                                        {
                                            "id": "provider-1",
                                            "function": {
                                                "name": "demo",
                                                "arguments": '{"value":1}',
                                            },
                                        }
                                    ],
                                },
                            }
                        ],
                        "usage": {"total_tokens": 10},
                    }
                ).encode(),
            )

        client = DeepSeekChatClient(
            api_key="test-only-secret",
            transport=transport,
        )
        result = client.complete(
            messages=[{"role": "user", "content": "test"}],
            tools=[],
        )

        self.assertEqual(
            captured["url"],
            "https://api.deepseek.com/chat/completions",
        )
        self.assertEqual(
            captured["body"]["model"],
            "deepseek-v4-flash",
        )
        self.assertEqual(
            captured["body"]["thinking"],
            {"type": "disabled"},
        )
        self.assertEqual(result.tool_calls[0].tool_name, "demo")
        self.assertNotIn(
            "test-only-secret",
            json.dumps(result.raw_response),
        )
        self.assertNotIn("test-only-secret", repr(client))

    def test_non_object_arguments_are_rejected(self) -> None:
        def transport(url, body, headers, timeout):
            return HttpResponseData(
                200,
                json.dumps(
                    {
                        "choices": [
                            {
                                "finish_reason": "tool_calls",
                                "message": {
                                    "content": None,
                                    "tool_calls": [
                                        {
                                            "id": "provider-1",
                                            "function": {
                                                "name": "demo",
                                                "arguments": "[]",
                                            },
                                        }
                                    ],
                                },
                            }
                        ]
                    }
                ).encode(),
            )

        with self.assertRaises(DeepSeekClientError):
            DeepSeekChatClient(
                api_key="test-only",
                transport=transport,
            ).complete(
                messages=[{"role": "user", "content": "test"}],
                tools=[],
            )

    def test_json_output_uses_standard_endpoint_without_tools(self) -> None:
        captured = {}

        def transport(url, body, headers, timeout):
            captured["url"] = url
            captured["body"] = json.loads(body)
            return HttpResponseData(
                200,
                json.dumps(
                    {
                        "choices": [
                            {
                                "finish_reason": "stop",
                                "message": {
                                    "content": '{"decision_type":"analysis","required_tools":["rank_products"]}'
                                },
                            }
                        ]
                    }
                ).encode(),
            )

        DeepSeekChatClient(
            api_key="test-only",
            transport=transport,
        ).complete_json(
            messages=[
                {
                    "role": "system",
                    "content": "只输出json对象。",
                }
            ]
        )

        self.assertEqual(
            captured["url"],
            "https://api.deepseek.com/chat/completions",
        )
        self.assertEqual(
            captured["body"]["response_format"],
            {"type": "json_object"},
        )
        self.assertNotIn("tools", captured["body"])
        self.assertNotIn("tool_choice", captured["body"])

    def test_strict_tools_use_beta_endpoint(self) -> None:
        captured = {}
        strict_tool = {
            "type": "function",
            "function": {
                "name": "demo",
                "description": "demo",
                "strict": True,
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
        }

        def transport(url, body, headers, timeout):
            captured["url"] = url
            captured["body"] = json.loads(body)
            return HttpResponseData(
                200,
                json.dumps(
                    {
                        "choices": [
                            {
                                "finish_reason": "tool_calls",
                                "message": {
                                    "content": "",
                                    "tool_calls": [
                                        {
                                            "id": "provider-1",
                                            "function": {
                                                "name": "demo",
                                                "arguments": "{}",
                                            },
                                        }
                                    ],
                                },
                            }
                        ]
                    }
                ).encode(),
            )

        DeepSeekChatClient(
            api_key="test-only",
            transport=transport,
        ).complete_strict_tools(
            messages=[{"role": "user", "content": "demo"}],
            tools=[strict_tool],
        )

        self.assertEqual(
            captured["url"],
            "https://api.deepseek.com/beta/chat/completions",
        )
        self.assertTrue(
            captured["body"]["tools"][0]["function"]["strict"]
        )
        self.assertNotIn("response_format", captured["body"])

    def test_strict_tools_can_lock_terminal_response_with_none(self) -> None:
        captured = {}

        def transport(url, body, headers, timeout):
            captured["body"] = json.loads(body)
            return HttpResponseData(
                200,
                json.dumps(
                    {
                        "choices": [
                            {
                                "finish_reason": "stop",
                                "message": {
                                    "content": '{"response_type":"report"}',
                                    "tool_calls": [],
                                },
                            }
                        ]
                    }
                ).encode(),
            )

        strict_tool = {
            "type": "function",
            "function": {
                "name": "demo",
                "description": "demo",
                "strict": True,
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
        }
        result = DeepSeekChatClient(
            api_key="test-only",
            transport=transport,
        ).complete_strict_tools(
            messages=[{"role": "user", "content": "demo"}],
            tools=[strict_tool],
            tool_choice="none",
        )

        self.assertEqual(captured["body"]["tool_choice"], "none")
        self.assertEqual(result.tool_calls, ())

    def test_strict_terminal_can_request_json_without_hiding_tools(self) -> None:
        captured = {}

        def transport(url, body, headers, timeout):
            captured["url"] = url
            captured["body"] = json.loads(body)
            return HttpResponseData(
                200,
                json.dumps(
                    {
                        "choices": [
                            {
                                "finish_reason": "stop",
                                "message": {
                                    "content": '{"response_type":"report"}',
                                    "tool_calls": [],
                                },
                            }
                        ]
                    }
                ).encode(),
            )

        strict_tool = {
            "type": "function",
            "function": {
                "name": "demo",
                "description": "demo",
                "strict": True,
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
        }
        DeepSeekChatClient(
            api_key="test-only",
            transport=transport,
        ).complete_strict_tools(
            messages=[
                {
                    "role": "system",
                    "content": "Return a json object matching the schema.",
                }
            ],
            tools=[strict_tool],
            tool_choice="none",
            response_format={"type": "json_object"},
        )

        self.assertEqual(
            captured["url"],
            "https://api.deepseek.com/beta/chat/completions",
        )
        self.assertEqual(captured["body"]["tool_choice"], "none")
        self.assertEqual(
            captured["body"]["response_format"],
            {"type": "json_object"},
        )
        self.assertEqual(len(captured["body"]["tools"]), 1)

    def test_strict_terminal_accepts_explicit_bounded_report_capacity(self) -> None:
        captured = {}

        def transport(url, body, headers, timeout):
            captured["body"] = json.loads(body)
            return HttpResponseData(
                200,
                json.dumps(
                    {
                        "choices": [
                            {
                                "finish_reason": "stop",
                                "message": {
                                    "content": "{}",
                                    "tool_calls": [],
                                },
                            }
                        ]
                    }
                ).encode(),
            )

        strict_tool = {
            "type": "function",
            "function": {
                "name": "demo",
                "strict": True,
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
        }
        DeepSeekChatClient(
            api_key="test-only",
            transport=transport,
        ).complete_strict_tools(
            messages=[{"role": "tool", "content": "{}"}],
            tools=[strict_tool],
            tool_choice="none",
            response_format={"type": "json_object"},
            max_tokens=8192,
        )
        self.assertEqual(captured["body"]["max_tokens"], 8192)

    def test_strict_terminal_rejects_unbounded_capacity(self) -> None:
        strict_tool = {
            "type": "function",
            "function": {
                "name": "demo",
                "strict": True,
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
        }
        with self.assertRaisesRegex(DeepSeekClientError, "max_tokens"):
            DeepSeekChatClient(api_key="test-only").complete_strict_tools(
                messages=[{"role": "tool", "content": "{}"}],
                tools=[strict_tool],
                tool_choice="none",
                response_format={"type": "json_object"},
                max_tokens=384001,
            )

    def test_strict_json_is_rejected_while_tool_choice_is_auto(self) -> None:
        strict_tool = {
            "type": "function",
            "function": {
                "name": "demo",
                "strict": True,
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
        }
        with self.assertRaisesRegex(
            DeepSeekClientError,
            "tool_choice=none",
        ):
            DeepSeekChatClient(api_key="test-only").complete_strict_tools(
                messages=[{"role": "user", "content": "json"}],
                tools=[strict_tool],
                tool_choice="auto",
                response_format={"type": "json_object"},
            )


if __name__ == "__main__":
    unittest.main()
