from __future__ import annotations

import unittest

from pydantic import ValidationError

from src.fact_builder import FactBuildContext, FactBuilder
from src.retail_cleaning import build_retail_data_layers
from src.retail_tools import RetailToolService
from src.tool_registry import RetailToolRegistry
from tests.test_retail_cleaning import sample_frame


def registry() -> RetailToolRegistry:
    layers = build_retail_data_layers(sample_frame())
    return RetailToolRegistry(RetailToolService(layers))


def context(call_id: str = "CALL-001") -> FactBuildContext:
    return FactBuildContext(
        session_id="SESSION-test",
        turn_id="TURN-001",
        call_id=call_id,
        source_result_path=(
            f"results/raw/test/calls/{call_id}/result.json"
        ),
    )


class FactBuilderTests(unittest.TestCase):
    def test_overview_generates_sequential_exact_facts(self) -> None:
        result = registry().execute(
            "get_sales_overview",
            {
                "period": "all_data",
                "start_date": None,
                "end_date": None,
                "include_incomplete_period_warning": True,
            },
        )

        facts = FactBuilder().build(result, context())

        self.assertEqual(facts[0].fact_id, "FACT-001")
        self.assertEqual(facts[0].metric, "sales_amount")
        self.assertEqual(facts[0].value, "4.47")
        self.assertEqual(facts[0].display_value, "£4.47")
        self.assertEqual(facts[0].unit, "GBP")

    def test_product_ranking_preserves_rank_and_dimensions(self) -> None:
        result = registry().execute(
            "rank_products",
            {
                "period": "all_data",
                "start_date": None,
                "end_date": None,
                "metric": "sales_amount",
                "top_n": 2,
            },
        )

        facts = FactBuilder().build(result, context())
        amount_facts = [
            fact for fact in facts if fact.metric == "sales_amount"
        ]
        associated_facts = [
            fact
            for fact in facts
            if fact.metric in {"sales_quantity", "order_count"}
        ]

        self.assertEqual([fact.rank for fact in amount_facts], [1])
        self.assertTrue(
            all(fact.rank is None for fact in associated_facts)
        )
        self.assertEqual(
            amount_facts[0].dimensions[0].name,
            "stock_code",
        )

    def test_region_rank_only_belongs_to_selected_metric(self) -> None:
        result = registry().execute(
            "analyze_regions",
            {
                "period": "all_data",
                "start_date": None,
                "end_date": None,
                "metric": "sales_quantity",
                "top_n": 2,
                "excluded_country": None,
            },
        )

        facts = FactBuilder().build(result, context())

        self.assertTrue(
            all(
                fact.rank is not None
                for fact in facts
                if fact.metric == "sales_quantity"
            )
        )
        self.assertTrue(
            all(
                fact.rank is None
                for fact in facts
                if fact.metric in {"sales_amount", "order_count"}
            )
        )

    def test_customer_facts_are_aggregate_only(self) -> None:
        result = registry().execute(
            "analyze_customers",
            {
                "period": "all_data",
                "start_date": None,
                "end_date": None,
                "include_coverage": True,
            },
        )

        facts = FactBuilder().build(result, context())
        serialized = str(
            [fact.model_dump(mode="json") for fact in facts]
        )

        self.assertNotIn("12345", serialized)
        self.assertNotIn("customer_id", serialized.lower())

    def test_absolute_source_path_is_rejected(self) -> None:
        result = registry().execute(
            "get_sales_overview",
            {
                "period": "all_data",
                "start_date": None,
                "end_date": None,
                "include_incomplete_period_warning": True,
            },
        )
        bad_context = FactBuildContext(
            session_id="SESSION-test",
            turn_id="TURN-001",
            call_id="CALL-001",
            source_result_path="D:/private/result.json",
        )

        with self.assertRaises(ValidationError):
            FactBuilder().build(result, bad_context)


if __name__ == "__main__":
    unittest.main()
