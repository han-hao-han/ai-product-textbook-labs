from __future__ import annotations

import json
import unittest

from src.agent_protocol import (
    AgentProtocolError,
    BoundaryResponse,
    ClarificationResponse,
    parse_control_response,
)
from src.prompt_contract import load_agent_prompts


class AgentProtocolAndPromptTests(unittest.TestCase):
    def test_versioned_prompts_are_loaded_with_hashes(self) -> None:
        prompts = load_agent_prompts()

        self.assertEqual(
            prompts.system.version,
            "1.5.6-h3-agent-system-v1",
        )
        self.assertEqual(len(prompts.system.sha256), 64)
        self.assertIn("一次模型响应最多选择一个工具", prompts.system.content)
        self.assertIn("不得自行做算术", prompts.report.content)
        self.assertIn(
            "数据概况不能替代用户对比较条件的确认",
            prompts.system.content,
        )
        self.assertIn("不要使用Markdown代码围栏", prompts.report.content)

    def test_parse_clarification_response(self) -> None:
        response = parse_control_response(
            json.dumps(
                {
                    "response_type": "clarification",
                    "message": "请一次性补充时间、指标和比较对象。",
                    "topics": [
                        "time_range",
                        "metric",
                        "comparison_dimension_or_objects",
                    ],
                },
                ensure_ascii=False,
            )
        )

        self.assertIsInstance(response, ClarificationResponse)
        self.assertEqual(len(response.topics), 3)

    def test_parse_boundary_response(self) -> None:
        response = parse_control_response(
            json.dumps(
                {
                    "response_type": "boundary",
                    "message": "缺少成本字段，无法计算利润。",
                    "missing_fields": ["cost", "profit"],
                    "supported_alternative": "按销售额或销量排名",
                },
                ensure_ascii=False,
            )
        )

        self.assertIsInstance(response, BoundaryResponse)

    def test_unknown_control_field_is_rejected(self) -> None:
        with self.assertRaises(AgentProtocolError):
            parse_control_response(
                json.dumps(
                    {
                        "response_type": "boundary",
                        "message": "不能执行。",
                        "missing_fields": [],
                        "supported_alternative": "历史趋势",
                        "reasoning": "不应暴露",
                    },
                    ensure_ascii=False,
                )
            )

    def test_single_fenced_json_block_is_normalized(self) -> None:
        response = parse_control_response(
            "已完成判断。\n```json\n"
            + json.dumps(
                {
                    "response_type": "boundary",
                    "message": "不支持预测。",
                    "missing_fields": ["external_drivers"],
                    "supported_alternative": "查看历史趋势",
                },
                ensure_ascii=False,
            )
            + "\n```"
        )

        self.assertIsInstance(response, BoundaryResponse)


if __name__ == "__main__":
    unittest.main()
