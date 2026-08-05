"""Mock-only tool registry backed by frozen H2 reference answers."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from src.fixed_question_validation import load_frozen_questions
from src.tool_schemas import TOOL_ARGUMENT_MODELS


class FrozenH2MockRegistry:
    """Return H2 answers through the frozen seven-tool interfaces."""

    names = tuple(TOOL_ARGUMENT_MODELS)

    def __init__(self) -> None:
        questions = load_frozen_questions()
        self.reference = {
            key: value["reference_answer"]
            for key, value in questions.items()
        }

    def provider_schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": f"H2 Mock：{name}",
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
        try:
            validated = TOOL_ARGUMENT_MODELS[
                tool_name
            ].model_validate(arguments)
        except (KeyError, ValidationError) as exc:
            raise ValueError(f"Mock工具参数无效：{exc}") from exc
        args = validated.model_dump(mode="json")
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
                "period": args.get("period", "all_data"),
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
        if tool_name == "get_sales_overview":
            return dict(self.reference["Q01"])
        if tool_name == "rank_products":
            if arguments["period"] == "custom":
                return {
                    "metric": "sales_amount_gbp",
                    "top_n": 3,
                    "ranking": self.reference["Q06"][
                        "top_3_products_in_peak_month"
                    ],
                }
            return dict(self.reference["Q02"])
        if tool_name == "analyze_regions":
            return dict(self.reference["Q03"])
        if tool_name == "analyze_time_trend":
            answer = self.reference["Q04"]
            peak = answer["peak_complete_month"]
            metrics = answer["peak_month_metrics"]
            return {
                "grain": "month",
                "metric": "sales_amount_gbp",
                "excluded_incomplete_periods": [
                    answer["excluded_incomplete_period"]
                ],
                "trend": [metrics],
                "peak_period": peak,
                "peak_period_metrics": metrics,
            }
        if tool_name == "analyze_customers":
            answer = self.reference["Q07"]
            return {
                **answer["known_customer_subset"],
                "privacy_note": answer["privacy_note"],
            }
        if tool_name == "compare_segments":
            return dict(self.reference["Q05"])
        if tool_name == "get_data_profile":
            raise ValueError(
                "Q01至Q10冻结问题不调用get_data_profile Mock"
            )
        raise ValueError(f"Mock不支持工具：{tool_name}")
