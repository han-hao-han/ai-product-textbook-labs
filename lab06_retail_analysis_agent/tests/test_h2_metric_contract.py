from __future__ import annotations

import json
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = PROJECT_ROOT / "config" / "h2_metric_contract.json"


class H2MetricContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    def test_h2_contract_is_fully_frozen(self) -> None:
        status = self.contract["status"]

        self.assertEqual(status["cleaning_and_metrics"], "frozen_by_user")
        self.assertEqual(
            status["fixed_validation_questions"],
            "frozen_by_user",
        )
        self.assertEqual(status["h2_overall"], "frozen")

    def test_post_dedup_classes_reconcile_to_total_rows(self) -> None:
        baseline = self.contract["real_data_baseline_after_keep_first"]
        classified_rows = sum(
            item["rows"] for item in baseline["classes"].values()
        )

        self.assertEqual(classified_rows, baseline["total_rows"])
        self.assertEqual(
            baseline["classes"]["sale"]["rows"],
            524878,
        )

    def test_metric_scopes_keep_customer_analysis_separate(self) -> None:
        metrics = self.contract["metrics"]

        self.assertEqual(metrics["sales_amount"]["scope"], "sales_fact")
        self.assertEqual(
            metrics["customer_count"]["scope"],
            "customer_fact",
        )
        self.assertTrue(
            metrics["customer_sales_amount"]["must_report_coverage"]
        )

    def test_unsupported_metrics_remain_explicitly_excluded(self) -> None:
        excluded = self.contract["excluded_metrics"]

        self.assertIn("net_sales_amount", excluded)
        self.assertIn("return_rate", excluded)
        self.assertIn("profit", excluded)
        self.assertIn("forecast", excluded)

    def test_public_contract_does_not_contain_customer_ids(self) -> None:
        serialized = json.dumps(self.contract, ensure_ascii=False)

        self.assertNotRegex(serialized, r"\b\d{5}\.0\b")
        self.assertEqual(
            self.contract["privacy"]["public_customer_outputs"],
            "仅展示聚合客户指标，不展示原始 CustomerID",
        )


if __name__ == "__main__":
    unittest.main()
