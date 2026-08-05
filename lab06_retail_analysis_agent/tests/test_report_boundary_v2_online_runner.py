from __future__ import annotations

import unittest

from src.deepseek_client import (
    ChatCompletionResult,
    DeepSeekClientError,
)
from scripts.run_report_boundary_v2_online import ApprovedV2Client


class FakeClient:
    def complete_json(self, *, messages):
        return ChatCompletionResult(
            finish_reason="stop",
            content="{}",
            tool_calls=(),
            raw_response={"mock": True},
            usage=None,
        )

    def complete_strict_tools(self, *, messages, tools):
        return self.complete_json(messages=messages)


class ReportBoundaryV2OnlineRunnerTests(unittest.TestCase):
    def test_attempt_cap_is_reserved_before_transport(self) -> None:
        client = ApprovedV2Client(FakeClient(), limit=2)

        client.complete_json(messages=[])
        client.complete_strict_tools(messages=[], tools=[{}])

        self.assertEqual(client.attempted, 2)
        self.assertEqual(client.completed, 2)
        with self.assertRaises(DeepSeekClientError):
            client.complete_json(messages=[])
        self.assertEqual(client.attempted, 2)


if __name__ == "__main__":
    unittest.main()
