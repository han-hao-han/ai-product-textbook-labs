from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.retail_cleaning import build_retail_data_layers  # noqa: E402


def sample_frame() -> pd.DataFrame:
    rows = [
        {
            "InvoiceNo": "100001",
            "StockCode": "A",
            "Description": " Alpha  product ",
            "Quantity": 2,
            "InvoiceDate": "2011-01-01 10:00",
            "UnitPrice": 1.234,
            "CustomerID": 12345.0,
            "Country": "United Kingdom ",
        },
        {
            "InvoiceNo": "100002",
            "StockCode": "A",
            "Description": "Alpha product",
            "Quantity": 1,
            "InvoiceDate": "2011-01-02 10:00",
            "UnitPrice": 2.0,
            "CustomerID": None,
            "Country": "France",
        },
        {
            "InvoiceNo": "C100003",
            "StockCode": "B",
            "Description": "Beta",
            "Quantity": -1,
            "InvoiceDate": "2011-01-03 10:00",
            "UnitPrice": 2.0,
            "CustomerID": 12346.0,
            "Country": "France",
        },
        {
            "InvoiceNo": "100004",
            "StockCode": "C",
            "Description": None,
            "Quantity": -3,
            "InvoiceDate": "2011-01-04 10:00",
            "UnitPrice": 0.0,
            "CustomerID": None,
            "Country": "United Kingdom",
        },
        {
            "InvoiceNo": "100005",
            "StockCode": "D",
            "Description": "Delta",
            "Quantity": 4,
            "InvoiceDate": "2011-01-05 10:00",
            "UnitPrice": 0.0,
            "CustomerID": 12347.0,
            "Country": "United Kingdom",
        },
        {
            "InvoiceNo": "A100006",
            "StockCode": "E",
            "Description": "Adjustment",
            "Quantity": 1,
            "InvoiceDate": "2011-01-06 10:00",
            "UnitPrice": -5.0,
            "CustomerID": None,
            "Country": "United Kingdom",
        },
    ]
    rows.append(dict(rows[0]))
    return pd.DataFrame(rows)


class RetailCleaningTests(unittest.TestCase):
    def test_layers_follow_frozen_classification_and_dedup(self) -> None:
        layers = build_retail_data_layers(sample_frame())

        self.assertEqual(len(layers.classified), 7)
        self.assertEqual(len(layers.sales_fact), 2)
        self.assertEqual(len(layers.customer_fact), 1)
        self.assertEqual(len(layers.exceptions), 4)
        self.assertEqual(
            layers.classified["record_class"].value_counts().to_dict(),
            {
                "sale": 3,
                "cancelled": 1,
                "inventory_adjustment": 1,
                "zero_price_non_sale": 1,
                "financial_adjustment": 1,
            },
        )

    def test_money_is_stored_as_exact_thousandths(self) -> None:
        layers = build_retail_data_layers(sample_frame())
        first_sale = layers.sales_fact.iloc[0]

        self.assertEqual(first_sale["unit_price_milli_gbp"], 1234)
        self.assertEqual(first_sale["line_amount_milli_gbp"], 2468)

    def test_customer_id_and_description_are_normalized(self) -> None:
        layers = build_retail_data_layers(sample_frame())

        self.assertEqual(layers.customer_fact.iloc[0]["customer_id"], "12345")
        self.assertEqual(
            layers.sales_fact.iloc[0]["description"],
            "Alpha product",
        )
        self.assertEqual(
            layers.sales_fact.iloc[0]["product_name"],
            "Alpha product",
        )

    def test_raw_frame_is_not_modified(self) -> None:
        frame = sample_frame()
        original = frame.copy(deep=True)

        build_retail_data_layers(frame)

        pd.testing.assert_frame_equal(frame, original)


if __name__ == "__main__":
    unittest.main()
