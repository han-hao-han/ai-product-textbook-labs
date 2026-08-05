"""Deterministic model-response Mock for the ten frozen H2 questions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from src.deepseek_client import (
    ChatCompletionResult,
    ProviderToolCall,
)
from src.fixed_question_validation import load_frozen_questions


DECISIONS_BY_QUESTION_ID: dict[str, dict[str, Any]] = {
    "Q01": {
        "decision_type": "analysis_recipe",
        "recipe_id": "sales_overview",
        "period": "all_data",
        "start_date": None,
        "end_date": None,
        "metric": "sales_amount",
        "top_n": None,
        "excluded_country": None,
        "profile_section": None,
    },
    "Q02": {
        "decision_type": "analysis_recipe",
        "recipe_id": "product_ranking",
        "period": "all_data",
        "start_date": None,
        "end_date": None,
        "metric": "sales_amount",
        "top_n": 5,
        "excluded_country": None,
        "profile_section": None,
    },
    "Q03": {
        "decision_type": "analysis_recipe",
        "recipe_id": "region_ranking",
        "period": "all_data",
        "start_date": None,
        "end_date": None,
        "metric": "sales_amount",
        "top_n": 5,
        "excluded_country": "United Kingdom",
        "profile_section": None,
    },
    "Q04": {
        "decision_type": "analysis_recipe",
        "recipe_id": "peak_complete_month",
        "period": "complete_months_only",
        "start_date": None,
        "end_date": None,
        "metric": "sales_amount",
        "top_n": None,
        "excluded_country": None,
        "profile_section": None,
    },
    "Q05": {
        "decision_type": "analysis_recipe",
        "recipe_id": "overview_and_uk_comparison",
        "period": "all_data",
        "start_date": None,
        "end_date": None,
        "metric": "sales_amount",
        "top_n": None,
        "excluded_country": None,
        "profile_section": None,
    },
    "Q06": {
        "decision_type": "analysis_recipe",
        "recipe_id": "peak_month_product_ranking",
        "period": "complete_months_only",
        "start_date": None,
        "end_date": None,
        "metric": "sales_amount",
        "top_n": 3,
        "excluded_country": None,
        "profile_section": None,
    },
    "Q07": {
        "decision_type": "analysis_recipe",
        "recipe_id": "overview_and_customer_coverage",
        "period": "all_data",
        "start_date": None,
        "end_date": None,
        "metric": "sales_amount",
        "top_n": None,
        "excluded_country": None,
        "profile_section": None,
    },
    "Q08": {
        "decision_type": "clarification",
        "message": "请一次性补充时间范围、核心指标以及比较维度或对象。",
        "topics": [
            "time_range",
            "metric",
            "comparison_dimension_or_objects",
        ],
    },
    "Q09": {
        "decision_type": "boundary",
        "message": "当前数据缺少成本和利润字段，不能计算利润或利润率。",
        "missing_fields": ["cost", "profit"],
        "supported_alternative": "按销售额或销量进行商品排名",
    },
    "Q10": {
        "decision_type": "boundary",
        "message": "实验不支持预测或自动补货，且缺少外部驱动和库存字段。",
        "missing_fields": [
            "forecast_drivers",
            "inventory",
        ],
        "supported_alternative": "展示历史月度销售趋势并标记不完整期间",
    },
}


def _content_result(
    payload: dict[str, Any],
    *,
    phase: str,
) -> ChatCompletionResult:
    return ChatCompletionResult(
        finish_reason="stop",
        content=json.dumps(payload, ensure_ascii=False),
        tool_calls=(),
        raw_response={
            "mock": True,
            "phase": phase,
            "payload": payload,
        },
        usage=None,
    )


def _ids(
    catalog: list[dict[str, Any]],
    *,
    source_tool: str | None = None,
    metric: str | None = None,
    fact_type: str | None = None,
    selection_role: str | None = None,
) -> list[str]:
    return [
        fact["fact_id"]
        for fact in catalog
        if (
            (source_tool is None or fact["source_tool"] == source_tool)
            and (metric is None or fact["metric"] == metric)
            and (
                fact_type is None
                or fact["fact_type"] == fact_type
            )
            and (
                selection_role is None
                or fact["selection_role"] == selection_role
            )
        )
    ]


def _semantic_plan(payload: dict[str, Any]) -> dict[str, Any]:
    recipe_id = payload["recipe_id"]
    catalog = payload["fact_catalog"]
    overview_ids = [
        fact_id
        for metric in (
            "sales_amount",
            "sales_quantity",
            "order_count",
            "average_order_value",
        )
        for fact_id in _ids(
            catalog,
            source_tool="get_sales_overview",
            metric=metric,
        )
    ]
    peak_ids = [
        *_ids(
            catalog,
            source_tool="analyze_time_trend",
            metric="peak_period",
        ),
        *_ids(
            catalog,
            source_tool="analyze_time_trend",
            metric="sales_amount",
            selection_role="selected_leader",
        ),
    ]
    product_rank_ids = _ids(
        catalog,
        source_tool="rank_products",
        metric="sales_amount",
        fact_type="ranked_metric",
    )
    region_rank_ids = _ids(
        catalog,
        source_tool="analyze_regions",
        metric="sales_amount",
        fact_type="ranked_metric",
    )
    segment_ids = _ids(
        catalog,
        source_tool="compare_segments",
    )
    customer_ids = [
        fact_id
        for metric in (
            "customer_count",
            "sales_row_coverage",
            "sales_amount_coverage",
        )
        for fact_id in _ids(
            catalog,
            source_tool="analyze_customers",
            metric=metric,
        )
    ]
    finding_blocks: list[dict[str, Any]]
    if recipe_id == "sales_overview":
        finding_blocks = [
            {
                "template_id": "metric_summary",
                "fact_ids": overview_ids,
            }
        ]
    elif recipe_id == "product_ranking":
        finding_blocks = [
            {
                "template_id": "ranked_entities_finding",
                "fact_ids": product_rank_ids,
            }
        ]
    elif recipe_id == "region_ranking":
        finding_blocks = [
            {
                "template_id": "ranked_entities_finding",
                "fact_ids": region_rank_ids,
            }
        ]
    elif recipe_id == "peak_complete_month":
        finding_blocks = [
            {
                "template_id": "peak_period_finding",
                "fact_ids": peak_ids,
            }
        ]
    elif recipe_id == "overview_and_uk_comparison":
        finding_blocks = [
            {
                "template_id": "metric_summary",
                "fact_ids": overview_ids,
            },
            {
                "template_id": "segment_comparison_finding",
                "fact_ids": segment_ids,
            },
        ]
    elif recipe_id == "peak_month_product_ranking":
        finding_blocks = [
            {
                "template_id": "peak_period_finding",
                "fact_ids": peak_ids,
            },
            {
                "template_id": "ranked_entities_finding",
                "fact_ids": product_rank_ids,
            },
        ]
    elif recipe_id == "overview_and_customer_coverage":
        finding_blocks = [
            {
                "template_id": "metric_summary",
                "fact_ids": overview_ids,
            },
            {
                "template_id": "customer_coverage_finding",
                "fact_ids": customer_ids,
            },
        ]
    elif recipe_id == "data_profile":
        profile_ids = _ids(
            catalog,
            source_tool="get_data_profile",
        )
        finding_blocks = [
            {
                "template_id": "profile_summary",
                "fact_ids": profile_ids,
            }
        ]
    else:
        raise ValueError(f"Mock没有语义计划：{recipe_id}")

    evidence_ids = list(
        dict.fromkeys(
            fact_id
            for block in finding_blocks
            for fact_id in block["fact_ids"]
        )
    )
    return {
        "schema_version": "1.5.6-h3-semantic-report-plan-v2.1",
        "session_id": payload["session_id"],
        "turn_id": payload["turn_id"],
        "recipe_id": recipe_id,
        "sections": [
            {
                "name": "用户问题与分析口径",
                "blocks": [
                    {
                        "template_id": "scope_from_facts",
                        "fact_ids": evidence_ids,
                    }
                ],
            },
            {
                "name": "关键经营发现",
                "blocks": finding_blocks,
            },
            {
                "name": "工具证据与图表",
                "blocks": [
                    {
                        "template_id": "tool_evidence_summary",
                        "fact_ids": evidence_ids,
                    }
                ],
            },
            {
                "name": "有限解释",
                "blocks": [
                    {
                        "template_id": "descriptive_only",
                        "fact_ids": evidence_ids,
                    }
                ],
            },
            {
                "name": "经营建议",
                "blocks": [
                    {
                        "template_id": "verify_with_additional_data",
                        "fact_ids": [],
                    }
                ],
            },
            {
                "name": "数据与分析限制",
                "blocks": [
                    {
                        "template_id": "data_limitations",
                        "fact_ids": [],
                    }
                ],
            },
        ],
    }


@dataclass
class FrozenQuestionV2_1MockClient:
    json_calls: int = 0
    strict_tool_calls: int = 0

    def __post_init__(self) -> None:
        questions = load_frozen_questions()
        self.question_id_by_text = {
            value["question"]: key for key, value in questions.items()
        }

    def complete_json(
        self,
        *,
        messages: list[dict[str, Any]],
    ) -> ChatCompletionResult:
        self.json_calls += 1
        payload = json.loads(messages[-1]["content"])
        phase = payload["phase"]
        if phase == "decision":
            question_id = self.question_id_by_text[
                payload["question"]
            ]
            return _content_result(
                DECISIONS_BY_QUESTION_ID[question_id],
                phase="decision",
            )
        if phase == "semantic_report":
            return _content_result(
                _semantic_plan(payload),
                phase="semantic_report",
            )
        raise AssertionError(f"未知Mock JSON阶段：{phase}")

    def complete_strict_tools(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ChatCompletionResult:
        self.strict_tool_calls += 1
        if len(tools) != 1:
            raise AssertionError("Mock每步必须只收到一个工具")
        payload = json.loads(messages[-1]["content"])
        contract = payload["step_contract"]
        tool_name = contract["tool_name"]
        if tools[0]["function"]["name"] != tool_name:
            raise AssertionError("Mock工具Schema与步骤不一致")
        return ChatCompletionResult(
            finish_reason="tool_calls",
            content=None,
            tool_calls=(
                ProviderToolCall(
                    provider_call_id=(
                        f"mock-provider-{self.strict_tool_calls:03d}"
                    ),
                    tool_name=tool_name,
                    arguments=contract["arguments"],
                ),
            ),
            raw_response={
                "mock": True,
                "phase": "strict_recipe_step",
                "step_id": contract["step_id"],
            },
            usage=None,
        )
