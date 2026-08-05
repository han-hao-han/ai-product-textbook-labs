from __future__ import annotations

import unittest

from src.agent_orchestrator import _runtime_system_prompt
from src.online_native_tool_candidate_tool_routing_v1 import (
    TOOL_ROUTING_PROMPT_PATH,
    project_runtime_messages_tool_routing_v1,
)
from src.prompt_contract import load_native_tool_agent_prompts_evidence_guard_v1


class ToolRoutingPromptV1Tests(unittest.TestCase):
    def test_prompt_is_additive_and_has_three_frozen_routing_rules(self) -> None:
        predecessor = (
            load_native_tool_agent_prompts_evidence_guard_v1().system.content
        )
        candidate = TOOL_ROUTING_PROMPT_PATH.read_text(
            encoding="utf-8"
        ).strip()
        self.assertTrue(candidate.startswith(predecessor))
        self.assertEqual(candidate.count("[TOOL-ROUTE-01]"), 1)
        self.assertEqual(candidate.count("[TOOL-ROUTE-02]"), 1)
        self.assertEqual(candidate.count("[TOOL-ROUTE-03]"), 1)
        self.assertIn("不要求先调用 `get_data_profile`", candidate)
        self.assertIn("商品或 StockCode 排名 → `rank_products`", candidate)

    def test_runtime_projection_replaces_only_the_system_prompt(self) -> None:
        prompts = load_native_tool_agent_prompts_evidence_guard_v1()
        runtime = _runtime_system_prompt(
            prompts,
            session_id="SESSION-tool-routing-test",
            turn_id="TURN-001",
        )
        projected = project_runtime_messages_tool_routing_v1(
            [{"role": "system", "content": runtime}]
        )
        content = projected[0]["content"]
        self.assertIn("[TOOL-ROUTE-01]", content)
        self.assertIn("[TOOL-ROUTE-02]", content)
        self.assertIn("[TOOL-ROUTE-03]", content)
        self.assertIn("chart_source_key", content)
        self.assertNotIn('"call_id"', content)


if __name__ == "__main__":
    unittest.main()
