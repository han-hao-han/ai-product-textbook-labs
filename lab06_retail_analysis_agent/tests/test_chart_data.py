from __future__ import annotations

import unittest

from src.chart_data import (
    ChartDataError,
    ChartSeries,
    build_chart_data,
    validate_chart_data,
)
from src.fact_builder import FactBuildContext, FactBuilder
from src.retail_cleaning import build_retail_data_layers
from src.retail_tools import RetailToolService
from src.tool_registry import RetailToolRegistry
from tests.test_retail_cleaning import sample_frame


class ChartDataTests(unittest.TestCase):
    def setUp(self) -> None:
        layers = build_retail_data_layers(sample_frame())
        self.registry = RetailToolRegistry(RetailToolService(layers))

    def _facts(self, result: dict, call_number: int) -> list:
        return FactBuilder().build(
            result,
            FactBuildContext(
                session_id="SESSION-test",
                turn_id="TURN-001",
                call_id=f"CALL-{call_number:03d}",
                source_result_path=(
                    "results/raw/test/calls/"
                    f"CALL-{call_number:03d}/result.json"
                ),
            ),
        )

    def test_all_four_whitelist_chart_types_are_built(self) -> None:
        cases = [
            (
                "top_n_horizontal_bar",
                "rank_products",
                {
                    "period": "all_data",
                    "start_date": None,
                    "end_date": None,
                    "metric": "sales_amount",
                    "top_n": 2,
                },
            ),
            (
                "vertical_bar",
                "analyze_regions",
                {
                    "period": "all_data",
                    "start_date": None,
                    "end_date": None,
                    "metric": "sales_amount",
                    "top_n": 2,
                    "excluded_country": None,
                },
            ),
            (
                "monthly_line",
                "analyze_time_trend",
                {
                    "period": "all_data",
                    "start_date": None,
                    "end_date": None,
                    "grain": "month",
                    "metric": "sales_amount",
                    "exclude_incomplete_periods": False,
                },
            ),
            (
                "two_segment_share_bar",
                "compare_segments",
                {
                    "period": "all_data",
                    "start_date": None,
                    "end_date": None,
                    "comparison": "united_kingdom_vs_other",
                },
            ),
        ]
        for call_number, (chart_type, tool_name, arguments) in enumerate(
            cases,
            start=1,
        ):
            with self.subTest(chart_type=chart_type):
                result = self.registry.execute(tool_name, arguments)
                facts = self._facts(result, call_number)
                chart = build_chart_data(
                    chart_id=f"CHART-{call_number:03d}",
                    chart_type=chart_type,
                    title=chart_type,
                    tool_result=result,
                    facts=facts,
                )

                self.assertEqual(chart.chart_type, chart_type)
                self.assertEqual(
                    len(chart.categories),
                    len(chart.series[0].values),
                )

    def test_changed_chart_value_is_rejected(self) -> None:
        result = self.registry.execute(
            "rank_products",
            {
                "period": "all_data",
                "start_date": None,
                "end_date": None,
                "metric": "sales_amount",
                "top_n": 2,
            },
        )
        facts = self._facts(result, 1)
        chart = build_chart_data(
            chart_id="CHART-001",
            chart_type="top_n_horizontal_bar",
            title="商品排名",
            tool_result=result,
            facts=facts,
        )
        bad_series = chart.series[0].model_copy(
            update={
                "values": ["999.99", *chart.series[0].values[1:]]
            }
        )
        changed = chart.model_copy(update={"series": [bad_series]})

        with self.assertRaises(ChartDataError):
            validate_chart_data(changed, facts)

    def test_cross_call_facts_are_rejected(self) -> None:
        result = self.registry.execute(
            "rank_products",
            {
                "period": "all_data",
                "start_date": None,
                "end_date": None,
                "metric": "sales_amount",
                "top_n": 2,
            },
        )
        facts = self._facts(result, 1)
        other_call_fact = facts[0].model_copy(
            update={"fact_id": "FACT-999", "call_id": "CALL-002"}
        )

        with self.assertRaises(ChartDataError):
            build_chart_data(
                chart_id="CHART-001",
                chart_type="top_n_horizontal_bar",
                title="商品排名",
                tool_result=result,
                facts=[*facts, other_call_fact],
            )


if __name__ == "__main__":
    unittest.main()
