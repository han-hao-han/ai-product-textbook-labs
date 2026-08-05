from __future__ import annotations

import calendar
import json
import unittest
from dataclasses import dataclass, field
from typing import Any, Callable

from src.agent_orchestrator import RetailAgentOrchestrator
from src.deepseek_client import (
    ChatCompletionResult,
    ProviderToolCall,
)
from src.report_validation import REPORT_SECTION_ORDER
from src.retail_cleaning import build_retail_data_layers
from src.retail_tools import RetailToolService
from src.tool_registry import RetailToolRegistry
from tests.test_retail_cleaning import sample_frame


def tool_response(
    call_id: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> ChatCompletionResult:
    return ChatCompletionResult(
        finish_reason="tool_calls",
        content=None,
        tool_calls=(
            ProviderToolCall(
                provider_call_id=call_id,
                tool_name=tool_name,
                arguments=arguments,
            ),
        ),
        raw_response={"mock": call_id},
        usage=None,
    )


def content_response(payload: dict[str, Any]) -> ChatCompletionResult:
    return ChatCompletionResult(
        finish_reason="stop",
        content=json.dumps(payload, ensure_ascii=False),
        tool_calls=(),
        raw_response={"mock": payload["response_type"]},
        usage=None,
    )


def valid_report_from_messages(
    messages: list[dict[str, Any]],
    *,
    chart_requests: list[dict[str, Any]] | None = None,
) -> ChatCompletionResult:
    system = messages[0]["content"]
    session_id = system.split("- session_id: ", 1)[1].splitlines()[0]
    turn_id = system.split("- turn_id: ", 1)[1].splitlines()[0]
    facts = []
    for message in messages:
        if message["role"] == "tool":
            facts.extend(json.loads(message["content"])["facts"])
    fact = facts[0]
    reference = {
        "fact_id": fact["fact_id"],
        "value": fact["value"],
        "display_value": fact["display_value"],
        "unit": fact["unit"],
        "rank": fact["rank"],
        "period": fact["analysis_scope"]["period"],
        "start_date": fact["analysis_scope"]["start_date"],
        "end_date": fact["analysis_scope"]["end_date"],
    }
    sections = []
    for name in REPORT_SECTION_ORDER:
        if name == "关键经营发现":
            claim = {
                "statement": f"程序结果为{fact['display_value']}。",
                "evidence": [reference],
            }
        else:
            claim = {
                "statement": "本节没有新增数值结论。",
                "evidence": [],
            }
        sections.append({"name": name, "claims": [claim]})
    return content_response(
        {
            "response_type": "report",
            "report": {
                "schema_version": "1.5.6-h3-report-draft-v1",
                "session_id": session_id,
                "turn_id": turn_id,
                "title": "经营分析报告",
                "sections": sections,
            },
            "chart_requests": chart_requests or [],
        }
    )


Step = ChatCompletionResult | Callable[
    [list[dict[str, Any]], list[dict[str, Any]]],
    ChatCompletionResult,
]


@dataclass
class ScriptedClient:
    steps: list[Step]
    seen_messages: list[list[dict[str, Any]]] = field(
        default_factory=list
    )

    def complete(self, *, messages, tools):
        self.seen_messages.append(messages)
        if not self.steps:
            raise AssertionError("unexpected model call")
        step = self.steps.pop(0)
        return step(messages, tools) if callable(step) else step


def registry() -> RetailToolRegistry:
    layers = build_retail_data_layers(sample_frame())
    return RetailToolRegistry(RetailToolService(layers))


class AgentOrchestratorTests(unittest.TestCase):
    def test_single_tool_to_validated_report(self) -> None:
        client = ScriptedClient(
            [
                tool_response(
                    "provider-1",
                    "get_sales_overview",
                    {
                        "period": "all_data",
                        "start_date": None,
                        "end_date": None,
                        "include_incomplete_period_warning": True,
                    },
                ),
                lambda messages, tools: valid_report_from_messages(
                    messages
                ),
            ]
        )

        outcome = RetailAgentOrchestrator(
            client=client,
            registry=registry(),
        ).run_turn(
            session_id="SESSION-mock",
            turn_id="TURN-001",
            question="请给出销售概览。",
        )

        self.assertEqual(outcome.status, "completed")
        self.assertEqual(outcome.model_response_count, 2)
        self.assertEqual(len(outcome.tool_calls), 1)
        self.assertEqual(outcome.report_validation.status, "passed")
        self.assertIn("[FACT-001]", outcome.report_markdown)

    def test_dependent_second_call_uses_peak_fact(self) -> None:
        captured = {}

        def second_call(messages, tools):
            first_payload = json.loads(messages[-1]["content"])
            peak_fact = next(
                fact
                for fact in first_payload["facts"]
                if fact["metric"] == "peak_period"
            )
            year, month = map(int, peak_fact["value"].split("-"))
            last_day = calendar.monthrange(year, month)[1]
            arguments = {
                "period": "custom",
                "start_date": f"{year:04d}-{month:02d}-01",
                "end_date": (
                    f"{year:04d}-{month:02d}-{last_day:02d}"
                ),
                "metric": "sales_amount",
                "top_n": 3,
            }
            captured["peak"] = peak_fact["value"]
            captured["arguments"] = arguments
            return tool_response(
                "provider-2",
                "rank_products",
                arguments,
            )

        client = ScriptedClient(
            [
                tool_response(
                    "provider-1",
                    "analyze_time_trend",
                    {
                        "period": "complete_months_only",
                        "start_date": None,
                        "end_date": None,
                        "grain": "month",
                        "metric": "sales_amount",
                        "exclude_incomplete_periods": True,
                    },
                ),
                second_call,
                lambda messages, tools: valid_report_from_messages(
                    messages,
                    chart_requests=[
                        {
                            "call_id": "CALL-002",
                            "chart_type": "top_n_horizontal_bar",
                            "title": "峰值月份商品排名",
                        }
                    ],
                ),
            ]
        )

        outcome = RetailAgentOrchestrator(
            client=client,
            registry=registry(),
        ).run_turn(
            session_id="SESSION-mock",
            turn_id="TURN-002",
            question="先找峰值完整月份，再列出该月商品前三名。",
        )

        self.assertEqual(outcome.status, "completed")
        self.assertEqual(len(outcome.tool_calls), 2)
        self.assertEqual(
            outcome.tool_calls[1].arguments,
            captured["arguments"],
        )
        self.assertTrue(
            captured["arguments"]["start_date"].startswith(
                captured["peak"]
            )
        )
        self.assertEqual(len(outcome.charts), 1)

    def test_clarification_happens_without_tool(self) -> None:
        client = ScriptedClient(
            [
                content_response(
                    {
                        "response_type": "clarification",
                        "message": "请补充时间、指标和比较对象。",
                        "topics": [
                            "time_range",
                            "metric",
                            "comparison_dimension_or_objects",
                        ],
                    }
                )
            ]
        )

        outcome = RetailAgentOrchestrator(
            client=client,
            registry=registry(),
        ).run_turn(
            session_id="SESSION-mock",
            turn_id="TURN-003",
            question="请比较销售表现。",
        )

        self.assertEqual(outcome.status, "needs_clarification")
        self.assertEqual(outcome.tool_calls, ())
        self.assertEqual(len(outcome.clarification.topics), 3)

    def test_boundary_happens_without_tool(self) -> None:
        client = ScriptedClient(
            [
                content_response(
                    {
                        "response_type": "boundary",
                        "message": "缺少成本与利润字段。",
                        "missing_fields": ["cost", "profit"],
                        "supported_alternative": "按销售额或销量排名",
                    }
                )
            ]
        )

        outcome = RetailAgentOrchestrator(
            client=client,
            registry=registry(),
        ).run_turn(
            session_id="SESSION-mock",
            turn_id="TURN-004",
            question="哪些商品最赚钱？",
        )

        self.assertEqual(outcome.status, "boundary")
        self.assertEqual(outcome.tool_calls, ())

    def test_multiple_calls_in_one_response_are_not_executed(self) -> None:
        response = ChatCompletionResult(
            finish_reason="tool_calls",
            content=None,
            tool_calls=(
                ProviderToolCall("one", "get_data_profile", {"section": "all"}),
                ProviderToolCall("two", "get_data_profile", {"section": "all"}),
            ),
            raw_response={"mock": "multiple"},
            usage=None,
        )

        outcome = RetailAgentOrchestrator(
            client=ScriptedClient([response]),
            registry=registry(),
        ).run_turn(
            session_id="SESSION-mock",
            turn_id="TURN-005",
            question="查看概况。",
        )

        self.assertEqual(outcome.status, "failed")
        self.assertEqual(outcome.tool_calls, ())
        self.assertIn("多个工具调用", outcome.error_message)

    def test_invalid_arguments_are_not_executed(self) -> None:
        outcome = RetailAgentOrchestrator(
            client=ScriptedClient(
                [
                    tool_response(
                        "provider-1",
                        "rank_products",
                        {
                            "period": "all_data",
                            "start_date": None,
                            "end_date": None,
                            "metric": "sales_amount",
                            "top_n": 999,
                        },
                    )
                ]
            ),
            registry=registry(),
        ).run_turn(
            session_id="SESSION-mock",
            turn_id="TURN-006",
            question="列出商品。",
        )

        self.assertEqual(outcome.status, "failed")
        self.assertEqual(outcome.error_stage, "argument_schema")
        self.assertEqual(outcome.tool_calls, ())

    def test_default_harness_still_stops_before_fifth_tool_call(self) -> None:
        client = ScriptedClient(
            [
                tool_response(
                    f"provider-{index}",
                    "get_data_profile",
                    {"section": section},
                )
                for index, section in enumerate(
                    ("summary", "customer_coverage", "classification", "all"),
                    start=1,
                )
            ]
            + [
                tool_response(
                    "provider-5",
                    "get_sales_overview",
                    {
                        "period": "all_data",
                        "start_date": None,
                        "end_date": None,
                        "include_incomplete_period_warning": True,
                    },
                )
            ]
        )
        outcome = RetailAgentOrchestrator(
            client=client,
            registry=registry(),
        ).run_turn(
            session_id="SESSION-default-four-tools",
            turn_id="TURN-001",
            question="连续查看多个数据部分。",
        )
        self.assertEqual(outcome.status, "failed")
        self.assertEqual(len(outcome.tool_calls), 4)
        self.assertIn("4次上限", outcome.error_message)


if __name__ == "__main__":
    unittest.main()
