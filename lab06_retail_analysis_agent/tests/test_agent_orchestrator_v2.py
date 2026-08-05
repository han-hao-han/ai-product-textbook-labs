from __future__ import annotations

import calendar
import json
import unittest
from dataclasses import dataclass, field
from typing import Any, Callable

from src.agent_decision_v2 import (
    BoundaryDecisionV2,
    ClarificationDecisionV2,
)
from src.agent_orchestrator_v2 import (
    RetailAgentOrchestratorV2,
    deepseek_strict_tool_schema,
)
from src.deepseek_client import ChatCompletionResult, ProviderToolCall
from src.report_validation import REPORT_SECTION_ORDER
from src.tool_schemas import TOOL_ARGUMENT_MODELS


KIND_BY_SECTION = {
    "用户问题与分析口径": "scope",
    "关键经营发现": "finding",
    "工具证据与图表": "evidence_note",
    "有限解释": "limited_interpretation",
    "经营建议": "recommendation",
    "数据与分析限制": "limitation",
}
JsonStep = ChatCompletionResult | Callable[
    [list[dict[str, Any]]],
    ChatCompletionResult,
]
ToolStep = ChatCompletionResult | Callable[
    [list[dict[str, Any]], list[dict[str, Any]]],
    ChatCompletionResult,
]


def content_response(payload: dict[str, Any]) -> ChatCompletionResult:
    return ChatCompletionResult(
        finish_reason="stop",
        content=json.dumps(payload, ensure_ascii=False),
        tool_calls=(),
        raw_response={"mock": payload.get("response_type", "decision")},
        usage=None,
    )


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


class FrozenAnswerRegistryV2:
    """Small H2-backed registry stub for the two Q06 tools."""

    def provider_schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": f"mock {name}",
                    "strict": True,
                    "parameters": model.model_json_schema(),
                },
            }
            for name, model in TOOL_ARGUMENT_MODELS.items()
        ]

    def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        validated = TOOL_ARGUMENT_MODELS[tool_name].model_validate(
            arguments
        )
        args = validated.model_dump(mode="json")
        if tool_name == "analyze_time_trend":
            data = {
                "grain": "month",
                "metric": "sales_amount_gbp",
                "excluded_incomplete_periods": ["2011-12"],
                "trend": [
                    {
                        "month": "2011-11",
                        "sales_quantity_items": 751377,
                        "order_count": 2769,
                        "sales_amount_gbp": "1503866.78",
                    }
                ],
                "peak_period": "2011-11",
                "peak_period_metrics": {
                    "month": "2011-11",
                    "sales_quantity_items": 751377,
                    "order_count": 2769,
                    "sales_amount_gbp": "1503866.78",
                },
            }
        elif tool_name == "rank_products":
            data = {
                "metric": "sales_amount_gbp",
                "top_n": 3,
                "ranking": [
                    {
                        "stock_code": "DOT",
                        "product_name": "DOTCOM POSTAGE",
                        "sales_quantity_items": 47,
                        "order_count": 47,
                        "sales_amount_gbp": "36905.40",
                    },
                    {
                        "stock_code": "23084",
                        "product_name": "RABBIT NIGHT LIGHT",
                        "sales_quantity_items": 14913,
                        "order_count": 487,
                        "sales_amount_gbp": "34478.40",
                    },
                    {
                        "stock_code": "22086",
                        "product_name": (
                            "PAPER CHAIN KIT 50'S CHRISTMAS"
                        ),
                        "sales_quantity_items": 7898,
                        "order_count": 390,
                        "sales_amount_gbp": "28955.54",
                    },
                ],
            }
        else:
            raise ValueError(f"该测试桩不支持工具：{tool_name}")
        return {
            "schema_version": "1.5.6-h3-tool-result-v1",
            "tool_name": tool_name,
            "arguments": args,
            "analysis_scope": {
                "fact_layer": "sales_fact",
                "period": args["period"],
                "start_date": args["start_date"],
                "end_date": args["end_date"],
                "row_count": 1,
            },
            "data": data,
            "warnings": [],
            "privacy": {
                "customer_id_values_exported": False,
                "public_customer_output": "aggregate_only",
            },
        }


@dataclass
class ScriptedV2Client:
    json_steps: list[JsonStep]
    tool_steps: list[ToolStep]
    json_calls: int = 0
    strict_tool_calls: int = 0
    seen_json_messages: list[list[dict[str, Any]]] = field(
        default_factory=list
    )

    def complete_json(self, *, messages):
        self.json_calls += 1
        self.seen_json_messages.append(messages)
        if not self.json_steps:
            raise AssertionError("unexpected JSON model call")
        step = self.json_steps.pop(0)
        return step(messages) if callable(step) else step

    def complete_strict_tools(self, *, messages, tools):
        self.strict_tool_calls += 1
        if not self.tool_steps:
            raise AssertionError("unexpected strict tool call")
        self.assert_one_strict_tool(tools)
        step = self.tool_steps.pop(0)
        return step(messages, tools) if callable(step) else step

    @staticmethod
    def assert_one_strict_tool(tools):
        if len(tools) != 1:
            raise AssertionError("expected one tool schema")
        if tools[0]["function"]["strict"] is not True:
            raise AssertionError("strict missing")


def q06_second_tool(messages, tools):
    payload = json.loads(messages[-1]["content"])
    peak = next(
        fact["value"]
        for fact in payload["facts"]
        if fact["metric"] == "peak_period"
    )
    year, month = map(int, peak.split("-"))
    last_day = calendar.monthrange(year, month)[1]
    return tool_response(
        "provider-2",
        "rank_products",
        {
            "period": "custom",
            "start_date": f"{peak}-01",
            "end_date": f"{peak}-{last_day:02d}",
            "metric": "sales_amount",
            "top_n": 3,
        },
    )


def final_report_v2(messages):
    user_payload = json.loads(messages[-1]["content"])
    catalog = user_payload["fact_catalog"]
    peak = next(
        fact for fact in catalog if fact["metric"] == "peak_period"
    )
    peak_sales = next(
        fact
        for fact in catalog
        if (
            fact["metric"] == "sales_amount"
            and fact["source_tool"] == "analyze_time_trend"
            and fact["selection_role"] == "selected_leader"
        )
    )
    sales_facts = [
        fact
        for fact in catalog
        if (
            fact["metric"] == "sales_amount"
            and fact["source_tool"] == "rank_products"
        )
    ]
    finding_ids = [peak["fact_id"], peak_sales["fact_id"]] + [
        fact["fact_id"] for fact in sales_facts
    ]
    sections = []
    for name in REPORT_SECTION_ORDER:
        kind = KIND_BY_SECTION[name]
        fact_ids = (
            []
            if kind in {"scope", "limitation"}
            else finding_ids
        )
        narrative = {
            "scope": "分析采用完整月份口径并观察峰值期间商品表现。",
            "finding": "程序证据显示峰值期间存在明确的商品销售表现排序。",
            "evidence_note": "当前轮工具证据共同支持该经营发现。",
            "limited_interpretation": "该结果仅支持描述性比较，不能证明具体原因。",
            "recommendation": "建议结合成本和库存等额外数据进一步评估。",
            "limitation": "当前分析不支持利润、预测或自动补货判断。",
        }[kind]
        sections.append(
            {
                "name": name,
                "claims": [
                    {
                        "claim_kind": kind,
                        "narrative": narrative,
                        "fact_ids": fact_ids,
                    }
                ],
            }
        )
    return content_response(
        {
            "response_type": "report",
            "report": {
                "schema_version": "1.5.6-h3-report-plan-v2",
                "session_id": "SESSION-v2",
                "turn_id": "TURN-001",
                "title": "完整月份峰值与商品表现",
                "sections": sections,
            },
            "chart_requests": [
                {
                    "call_id": "CALL-002",
                    "chart_type": "top_n_horizontal_bar",
                    "title": "峰值期间商品排名",
                }
            ],
        }
    )


class AgentOrchestratorV2Tests(unittest.TestCase):
    def test_provider_adapter_preserves_local_schema_but_removes_only_unsupported_strict_keywords(
        self,
    ) -> None:
        original = next(
            schema
            for schema in FrozenAnswerRegistryV2().provider_schemas()
            if schema["function"]["name"] == "analyze_regions"
        )
        adapted = deepseek_strict_tool_schema(original)
        original_text = json.dumps(original)
        adapted_text = json.dumps(adapted)

        self.assertIn("minLength", original_text)
        self.assertIn("maxLength", original_text)
        self.assertNotIn("minLength", adapted_text)
        self.assertNotIn("maxLength", adapted_text)
        self.assertIn('"strict": true', adapted_text)
        self.assertIn("additionalProperties", adapted_text)

    def test_q06_gate_tools_and_program_finalization(self) -> None:
        client = ScriptedV2Client(
            json_steps=[
                content_response(
                    {
                        "decision_type": "analysis",
                        "required_tools": [
                            "analyze_time_trend",
                            "rank_products",
                        ],
                    }
                ),
                final_report_v2,
            ],
            tool_steps=[
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
                q06_second_tool,
            ],
        )

        outcome = RetailAgentOrchestratorV2(
            client=client,
            registry=FrozenAnswerRegistryV2(),
        ).run_turn(
            session_id="SESSION-v2",
            turn_id="TURN-001",
            question="先找出峰值完整月份，再查看该月商品排名。",
        )

        self.assertEqual(outcome.status, "completed")
        self.assertEqual(outcome.model_response_count, 4)
        self.assertEqual(
            [call.tool_name for call in outcome.tool_calls],
            ["analyze_time_trend", "rank_products"],
        )
        self.assertEqual(
            outcome.tool_calls[1].arguments["start_date"],
            "2011-11-01",
        )
        self.assertEqual(outcome.report_validation.status, "passed")
        self.assertIn("£1,503,866.78", outcome.report_markdown)
        self.assertIn("£36,905.40", outcome.report_markdown)
        self.assertNotIn(
            "£36,905.40",
            outcome.report_response.model_dump_json(),
        )
        self.assertEqual(len(outcome.charts), 1)
        self.assertEqual(client.json_calls, 2)
        self.assertEqual(client.strict_tool_calls, 2)
        report_payload = json.loads(
            client.seen_json_messages[1][-1]["content"]
        )
        catalog_text = json.dumps(
            report_payload["fact_catalog"],
            ensure_ascii=False,
        )
        for fact_summary in report_payload["fact_catalog"]:
            self.assertTrue(
                {
                    "value",
                    "display_value",
                    "unit",
                    "rank",
                    "analysis_scope",
                    "dimensions",
                }.isdisjoint(fact_summary)
            )
        self.assertNotIn("2011-11", catalog_text)
        self.assertNotIn("1503866.78", catalog_text)
        self.assertNotIn("DOTCOM POSTAGE", catalog_text)

    def test_q08_stops_at_json_clarification_gate(self) -> None:
        client = ScriptedV2Client(
            json_steps=[
                content_response(
                    {
                        "decision_type": "clarification",
                        "message": "请补充时间范围、指标和比较对象。",
                        "topics": [
                            "time_range",
                            "metric",
                            "comparison_dimension_or_objects",
                        ],
                    }
                )
            ],
            tool_steps=[],
        )

        outcome = RetailAgentOrchestratorV2(
            client=client,
            registry=FrozenAnswerRegistryV2(),
        ).run_turn(
            session_id="SESSION-v2",
            turn_id="TURN-002",
            question="请比较销售表现。",
        )

        self.assertEqual(outcome.status, "needs_clarification")
        self.assertIsInstance(
            outcome.decision,
            ClarificationDecisionV2,
        )
        self.assertEqual(outcome.model_response_count, 1)
        self.assertEqual(client.strict_tool_calls, 0)

    def test_q09_stops_at_json_boundary_gate(self) -> None:
        client = ScriptedV2Client(
            json_steps=[
                content_response(
                    {
                        "decision_type": "boundary",
                        "message": "缺少成本与利润字段。",
                        "missing_fields": ["cost", "profit"],
                        "supported_alternative": "按销售额或销量排名",
                    }
                )
            ],
            tool_steps=[],
        )

        outcome = RetailAgentOrchestratorV2(
            client=client,
            registry=FrozenAnswerRegistryV2(),
        ).run_turn(
            session_id="SESSION-v2",
            turn_id="TURN-003",
            question="请计算商品利润。",
        )

        self.assertEqual(outcome.status, "boundary")
        self.assertIsInstance(outcome.decision, BoundaryDecisionV2)
        self.assertEqual(client.strict_tool_calls, 0)

    def test_numeric_model_report_is_rejected_before_render(self) -> None:
        def invalid_final(messages):
            response = final_report_v2(messages)
            payload = json.loads(response.content)
            payload["report"]["sections"][1]["claims"][0][
                "narrative"
            ] = "模型擅自写入增长率百分之30。"
            return content_response(payload)

        client = ScriptedV2Client(
            json_steps=[
                content_response(
                    {
                        "decision_type": "analysis",
                        "required_tools": ["analyze_time_trend"],
                    }
                ),
                invalid_final,
            ],
            tool_steps=[
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
                )
            ],
        )

        outcome = RetailAgentOrchestratorV2(
            client=client,
            registry=FrozenAnswerRegistryV2(),
        ).run_turn(
            session_id="SESSION-v2",
            turn_id="TURN-001",
            question="查看峰值月份。",
        )

        self.assertEqual(outcome.status, "failed")
        self.assertEqual(
            outcome.error_stage,
            "report_finalization",
        )
        self.assertIn(
            "模型叙述和标题不得包含数字",
            outcome.error_message,
        )
        self.assertIsNone(outcome.report_markdown)


if __name__ == "__main__":
    unittest.main()
