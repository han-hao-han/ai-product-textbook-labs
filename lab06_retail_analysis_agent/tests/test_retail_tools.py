from __future__ import annotations

import unittest

from src.retail_cleaning import build_retail_data_layers
from src.retail_tools import RetailToolService
from src.tool_registry import (
    RetailToolRegistry,
    ToolExecutionError,
)
from tests.test_retail_cleaning import sample_frame


def sample_registry() -> RetailToolRegistry:
    layers = build_retail_data_layers(sample_frame())
    return RetailToolRegistry(RetailToolService(layers))


class RetailToolTests(unittest.TestCase):
    def test_registry_rejects_non_whitelisted_tool(self) -> None:
        with self.assertRaises(ToolExecutionError):
            sample_registry().execute(
                "run_python",
                {"code": "print('unsafe')"},
            )

    def test_sales_overview_uses_h2_sales_fact(self) -> None:
        result = sample_registry().execute(
            "get_sales_overview",
            {
                "period": "all_data",
                "start_date": None,
                "end_date": None,
                "include_incomplete_period_warning": True,
            },
        )

        self.assertEqual(result["data"]["sales_amount_gbp"], "4.47")
        self.assertEqual(result["data"]["order_count"], 2)

    def test_customer_tool_never_returns_identifier_values(self) -> None:
        result = sample_registry().execute(
            "analyze_customers",
            {
                "period": "all_data",
                "start_date": None,
                "end_date": None,
                "include_coverage": True,
            },
        )
        serialized = str(result)

        self.assertNotIn("12345", serialized)
        self.assertNotIn("customer_id", result["data"])
        self.assertEqual(result["data"]["customer_count"], 1)

    def test_custom_date_range_is_inclusive_by_calendar_day(self) -> None:
        result = sample_registry().execute(
            "rank_products",
            {
                "period": "custom",
                "start_date": "2011-01-02",
                "end_date": "2011-01-02",
                "metric": "sales_amount",
                "top_n": 1,
            },
        )

        self.assertEqual(result["data"]["ranking"][0]["sales_amount_gbp"], "2.00")

    def test_tool_result_keeps_scope_and_privacy_metadata(self) -> None:
        result = sample_registry().execute(
            "get_data_profile",
            {"section": "summary"},
        )

        self.assertEqual(result["tool_name"], "get_data_profile")
        self.assertFalse(result["privacy"]["customer_id_values_exported"])
        self.assertIn("analysis_scope", result)


if __name__ == "__main__":
    unittest.main()
