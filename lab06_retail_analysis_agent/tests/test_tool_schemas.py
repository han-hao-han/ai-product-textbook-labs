from __future__ import annotations

import unittest

from pydantic import ValidationError

from src.tool_schemas import (
    GetSalesOverviewArguments,
    RankProductsArguments,
    TOOL_ARGUMENT_MODELS,
)


class ToolSchemaTests(unittest.TestCase):
    def test_exactly_seven_argument_models_are_frozen(self) -> None:
        self.assertEqual(
            tuple(TOOL_ARGUMENT_MODELS),
            (
                "get_data_profile",
                "get_sales_overview",
                "rank_products",
                "analyze_regions",
                "analyze_time_trend",
                "analyze_customers",
                "compare_segments",
            ),
        )

    def test_all_provider_object_fields_are_required_and_closed(
        self,
    ) -> None:
        for model in TOOL_ARGUMENT_MODELS.values():
            schema = model.model_json_schema()
            self.assertFalse(schema["additionalProperties"])
            self.assertEqual(
                set(schema["properties"]),
                set(schema["required"]),
            )

    def test_extra_fields_and_coercion_are_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            RankProductsArguments.model_validate(
                {
                    "period": "all_data",
                    "start_date": None,
                    "end_date": None,
                    "metric": "sales_amount",
                    "top_n": "5",
                    "python": "print('unsafe')",
                }
            )

    def test_custom_period_requires_valid_ordered_dates(self) -> None:
        with self.assertRaises(ValidationError):
            GetSalesOverviewArguments.model_validate(
                {
                    "period": "custom",
                    "start_date": "2011-12-02",
                    "end_date": "2011-12-01",
                    "include_incomplete_period_warning": True,
                }
            )

    def test_non_custom_period_requires_null_dates(self) -> None:
        with self.assertRaises(ValidationError):
            GetSalesOverviewArguments.model_validate(
                {
                    "period": "all_data",
                    "start_date": "2011-01-01",
                    "end_date": None,
                    "include_incomplete_period_warning": True,
                }
            )


if __name__ == "__main__":
    unittest.main()
