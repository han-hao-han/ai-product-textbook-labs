from __future__ import annotations

import calendar
import unittest
from typing import Any

from pydantic import ValidationError

from src.agent_orchestrator import RetailAgentOrchestrator
from src.fixed_question_validation import (
    load_frozen_questions,
    validate_fixed_question,
)
from src.tool_schemas import TOOL_ARGUMENT_MODELS
from tests.test_agent_orchestrator import (
    ScriptedClient,
    content_response,
    tool_response,
    valid_report_from_messages,
)


class FrozenAnswerRegistry:
    """Mock tool registry backed by the frozen H2 answers."""

    names = (
        "get_data_profile",
        "get_sales_overview",
        "rank_products",
        "analyze_regions",
        "analyze_time_trend",
        "analyze_customers",
        "compare_segments",
    )

    def __init__(self) -> None:
        self.questions = load_frozen_questions()

    def provider_schemas(self) -> list[dict[str, Any]]:
        return []

    def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            validated = TOOL_ARGUMENT_MODELS[
                tool_name
            ].model_validate(arguments)
        except (KeyError, ValidationError) as exc:
            raise ValueError(str(exc)) from exc
        args = validated.model_dump(mode="json")
        period = args.get("period", "all_data")
        data = self._data(tool_name, args)
        return {
            "schema_version": "1.5.6-h3-tool-result-v1",
            "tool_name": tool_name,
            "arguments": args,
            "analysis_scope": {
                "fact_layer": (
                    "customer_fact"
                    if tool_name == "analyze_customers"
                    else "sales_fact"
                ),
                "period": period,
                "start_date": args.get("start_date"),
                "end_date": args.get("end_date"),
                "row_count": 1,
            },
            "data": data,
            "warnings": [],
            "privacy": {
                "customer_id_values_exported": False,
                "public_customer_output": "aggregate_only",
            },
        }

    def _data(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        reference = {
            key: value["reference_answer"]
            for key, value in self.questions.items()
        }
        if tool_name == "get_sales_overview":
            return dict(reference["Q01"])
        if tool_name == "rank_products":
            if arguments["period"] == "custom":
                return {
                    "metric": "sales_amount_gbp",
                    "top_n": 3,
                    "ranking": reference["Q06"][
                        "top_3_products_in_peak_month"
                    ],
                }
            return dict(reference["Q02"])
        if tool_name == "analyze_regions":
            return dict(reference["Q03"])
        if tool_name == "analyze_time_trend":
            peak = reference["Q04"]["peak_complete_month"]
            metrics = reference["Q04"]["peak_month_metrics"]
            return {
                "grain": "month",
                "metric": "sales_amount_gbp",
                "excluded_incomplete_periods": [
                    reference["Q04"][
                        "excluded_incomplete_period"
                    ]
                ],
                "trend": [metrics],
                "peak_period": peak,
                "peak_period_metrics": metrics,
            }
        if tool_name == "analyze_customers":
            return {
                **reference["Q07"]["known_customer_subset"],
                "privacy_note": reference["Q07"]["privacy_note"],
            }
        if tool_name == "compare_segments":
            return dict(reference["Q05"])
        raise ValueError(f"mock不支持工具：{tool_name}")


def common_period() -> dict[str, Any]:
    return {
        "period": "all_data",
        "start_date": None,
        "end_date": None,
    }


def report_step(messages, tools):
    return valid_report_from_messages(messages)


def scripts() -> dict[str, list]:
    all_data = common_period()

    def q06_rank(messages, tools):
        first_tool = next(
            message
            for message in reversed(messages)
            if message["role"] == "tool"
        )
        import json

        facts = json.loads(first_tool["content"])["facts"]
        peak = next(
            fact["value"]
            for fact in facts
            if fact["metric"] == "peak_period"
        )
        year, month = map(int, peak.split("-"))
        end = calendar.monthrange(year, month)[1]
        return tool_response(
            "provider-2",
            "rank_products",
            {
                "period": "custom",
                "start_date": f"{peak}-01",
                "end_date": f"{peak}-{end:02d}",
                "metric": "sales_amount",
                "top_n": 3,
            },
        )

    return {
        "Q01": [
            tool_response(
                "provider-1",
                "get_sales_overview",
                {
                    **all_data,
                    "include_incomplete_period_warning": True,
                },
            ),
            report_step,
        ],
        "Q02": [
            tool_response(
                "provider-1",
                "rank_products",
                {
                    **all_data,
                    "metric": "sales_amount",
                    "top_n": 5,
                },
            ),
            report_step,
        ],
        "Q03": [
            tool_response(
                "provider-1",
                "analyze_regions",
                {
                    **all_data,
                    "metric": "sales_amount",
                    "top_n": 5,
                    "excluded_country": "United Kingdom",
                },
            ),
            report_step,
        ],
        "Q04": [
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
            report_step,
        ],
        "Q05": [
            tool_response(
                "provider-1",
                "get_sales_overview",
                {
                    **all_data,
                    "include_incomplete_period_warning": True,
                },
            ),
            tool_response(
                "provider-2",
                "compare_segments",
                {
                    **all_data,
                    "comparison": "united_kingdom_vs_other",
                },
            ),
            report_step,
        ],
        "Q06": [
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
            q06_rank,
            report_step,
        ],
        "Q07": [
            tool_response(
                "provider-1",
                "get_sales_overview",
                {
                    **all_data,
                    "include_incomplete_period_warning": True,
                },
            ),
            tool_response(
                "provider-2",
                "analyze_customers",
                {
                    **all_data,
                    "include_coverage": True,
                },
            ),
            report_step,
        ],
        "Q08": [
            content_response(
                {
                    "response_type": "clarification",
                    "message": "请补充时间范围、核心指标和比较对象。",
                    "topics": [
                        "time_range",
                        "metric",
                        "comparison_dimension_or_objects",
                    ],
                }
            )
        ],
        "Q09": [
            content_response(
                {
                    "response_type": "boundary",
                    "message": "数据缺少成本和利润，无法计算。",
                    "missing_fields": ["cost", "profit"],
                    "supported_alternative": "按销售额或销量进行商品排名",
                }
            )
        ],
        "Q10": [
            content_response(
                {
                    "response_type": "boundary",
                    "message": "不支持预测和自动补货。",
                    "missing_fields": [
                        "inventory",
                        "external_drivers",
                    ],
                    "supported_alternative": "展示历史月度销售趋势并标记2011-12不完整",
                    "boundary_codes": [
                        "forecasting_unsupported",
                        "automatic_replenishment_unsupported",
                    ],
                }
            )
        ],
    }


class FixedQuestionEndToEndTests(unittest.TestCase):
    def test_all_ten_frozen_questions_pass_mock_agent_e2e(self) -> None:
        questions = load_frozen_questions()
        outcomes = {}
        for index, (question_id, steps) in enumerate(
            scripts().items(),
            start=1,
        ):
            outcome = RetailAgentOrchestrator(
                client=ScriptedClient(steps),
                registry=FrozenAnswerRegistry(),
            ).run_turn(
                session_id="SESSION-fixed-mock",
                turn_id=f"TURN-{index:03d}",
                question=questions[question_id]["question"],
            )
            outcomes[question_id] = outcome

        validations = {
            question_id: validate_fixed_question(
                question_id,
                outcome,
            )
            for question_id, outcome in outcomes.items()
        }

        self.assertEqual(
            set(validations),
            {f"Q{index:02d}" for index in range(1, 11)},
        )
        self.assertEqual(
            {
                question_id: validation.status
                for question_id, validation in validations.items()
            },
            {
                **{
                    f"Q{index:02d}": "protocol_and_dataflow_passed"
                    for index in range(1, 8)
                },
                **{
                    f"Q{index:02d}": (
                        "passed_deterministic_pending_manual_review"
                    )
                    for index in range(8, 11)
                },
            },
        )
        self.assertTrue(
            all(
                validation.tool_reference_answer_status
                in {"passed", "not_applicable"}
                for validation in validations.values()
            )
        )
        self.assertEqual(
            outcomes["Q06"].tool_calls[1].arguments["start_date"],
            "2011-11-01",
        )
        self.assertEqual(outcomes["Q08"].tool_calls, ())
        self.assertEqual(outcomes["Q09"].tool_calls, ())
        self.assertEqual(outcomes["Q10"].tool_calls, ())

    def test_changed_h2_value_is_detected(self) -> None:
        questions = load_frozen_questions()
        outcome = RetailAgentOrchestrator(
            client=ScriptedClient(scripts()["Q01"]),
            registry=FrozenAnswerRegistry(),
        ).run_turn(
            session_id="SESSION-fixed-mock",
            turn_id="TURN-001",
            question=questions["Q01"]["question"],
        )
        outcome.tool_calls[0].result["data"][
            "sales_amount_gbp"
        ] = "0.00"

        validation = validate_fixed_question("Q01", outcome)

        self.assertEqual(validation.status, "failed")
        self.assertIn(
            "reference_answer.sales_amount_gbp",
            {issue.path for issue in validation.issues},
        )


if __name__ == "__main__":
    unittest.main()
