from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.cleaning_profile import build_cleaning_profile  # noqa: E402


def sample_frame() -> pd.DataFrame:
    rows = [
        {
            "InvoiceNo": "100001",
            "StockCode": "A",
            "Description": "Alpha",
            "Quantity": 2,
            "InvoiceDate": "2011-01-01 10:00",
            "UnitPrice": 1.5,
            "CustomerID": "12345",
            "Country": "United Kingdom",
        },
        {
            "InvoiceNo": "100002",
            "StockCode": "A",
            "Description": "Alpha revised",
            "Quantity": 1,
            "InvoiceDate": "2011-01-02 10:00",
            "UnitPrice": 2.0,
            "CustomerID": None,
            "Country": "United Kingdom ",
        },
        {
            "InvoiceNo": "C100003",
            "StockCode": "B",
            "Description": "Beta",
            "Quantity": -1,
            "InvoiceDate": "2011-01-03 10:00",
            "UnitPrice": 2.0,
            "CustomerID": "12346",
            "Country": "France",
        },
        {
            "InvoiceNo": "100004",
            "StockCode": "C",
            "Description": None,
            "Quantity": -3,
            "InvoiceDate": "2011-01-04 10:00",
            "UnitPrice": 1.0,
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
            "CustomerID": "12347",
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


class CleaningProfileTests(unittest.TestCase):
    def test_profile_classifies_every_row_once(self) -> None:
        frame = sample_frame()
        profile = build_cleaning_profile(frame, top_n=5)

        classified_rows = sum(
            item["rows"] for item in profile["record_classification"]
        )
        classified_rows_after_keep_first = sum(
            item["rows"]
            for item in profile[
                "record_classification_after_keep_first"
            ]
        )
        self.assertEqual(classified_rows, len(frame))
        self.assertEqual(classified_rows_after_keep_first, len(frame) - 1)
        self.assertEqual(
            profile["signal_counts"]["normal_sales_candidate_rows"], 3
        )
        self.assertEqual(
            profile["signal_counts"]["negative_quantity_no_c_rows"], 1
        )

    def test_duplicate_sensitivity_is_explicit(self) -> None:
        profile = build_cleaning_profile(sample_frame(), top_n=5)
        sensitivity = profile["exact_duplicate_sensitivity"]

        self.assertEqual(sensitivity["rows_removed_if_keep_first"], 1)
        self.assertEqual(
            sensitivity["difference_if_keep_first"]["rows"], 1.0
        )
        self.assertEqual(
            sensitivity["difference_if_keep_first"]["quantity_sum"], 2.0
        )
        self.assertEqual(
            sensitivity["difference_if_keep_first"][
                "known_customer_mechanical_value_gbp"
            ],
            3.0,
        )
        self.assertEqual(
            sensitivity["normal_candidate_after_keep_first"][
                "known_customer_value_ratio"
            ],
            0.6,
        )

    def test_customer_values_are_not_exported(self) -> None:
        profile = build_cleaning_profile(sample_frame(), top_n=5)

        self.assertNotIn("12345", str(profile))
        self.assertFalse(
            profile["customer_coverage_for_normal_sales_candidate"][
                "customer_id_values_exported"
            ]
        )

    def test_description_and_country_inconsistency_are_counted(self) -> None:
        profile = build_cleaning_profile(sample_frame(), top_n=5)

        self.assertEqual(
            profile["product_description_consistency"][
                "stock_codes_with_multiple_normalized_descriptions"
            ],
            1,
        )
        self.assertEqual(
            profile["country_normalization"]["rows_changed_by_trim"], 1
        )

    def test_top_n_must_be_positive(self) -> None:
        with self.assertRaisesRegex(ValueError, "top_n"):
            build_cleaning_profile(sample_frame(), top_n=0)


if __name__ == "__main__":
    unittest.main()
