from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.data_audit import (  # noqa: E402
    DataAuditError,
    build_audit_report,
    masked_preview,
)


def sample_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "InvoiceNo": ["100001", "C100002", "c100003", "100004"],
            "StockCode": ["A", "B", "C", "D"],
            "Description": ["Alpha", "Beta", None, "Delta"],
            "Quantity": [2, -1, 1, -3],
            "InvoiceDate": [
                "2011-01-01 10:00",
                "2011-01-02 10:00",
                "2011-01-03 10:00",
                "not-a-date",
            ],
            "UnitPrice": [1.5, 2.0, 0.0, -1.0],
            "CustomerID": ["12345", "12346", None, "12347"],
            "Country": ["United Kingdom"] * 4,
        }
    )


class DataAuditTests(unittest.TestCase):
    def test_build_audit_report_keeps_signals_separate(self) -> None:
        report = build_audit_report(sample_frame())

        self.assertEqual(report["quantity"]["negative_rows"], 2)
        self.assertEqual(
            report["cancellation_signals"]["case_insensitive_c_rows"], 2
        )
        self.assertEqual(
            report["signal_overlap"]["c_prefix_and_negative_quantity_rows"], 1
        )
        self.assertEqual(
            report["signal_overlap"]["c_prefix_and_positive_quantity_rows"], 1
        )
        self.assertEqual(
            report["signal_overlap"]["no_c_prefix_and_negative_quantity_rows"], 1
        )
        self.assertEqual(
            report["interpretation_status"]["returns"],
            "pending_h2_interpretation",
        )

    def test_report_and_preview_do_not_export_customer_ids(self) -> None:
        frame = sample_frame()
        report = build_audit_report(frame)
        preview = masked_preview(frame, 4)

        self.assertNotIn("12345", str(report))
        self.assertNotIn("12345", str(preview))
        self.assertEqual(preview[0]["CustomerID"], "<present>")
        self.assertEqual(preview[2]["CustomerID"], "<missing>")

    def test_missing_required_column_is_rejected(self) -> None:
        frame = sample_frame().drop(columns=["Country"])

        with self.assertRaisesRegex(DataAuditError, "Country"):
            build_audit_report(frame)


if __name__ == "__main__":
    unittest.main()
