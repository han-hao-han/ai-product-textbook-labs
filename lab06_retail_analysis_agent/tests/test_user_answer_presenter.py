from __future__ import annotations

import json
import unittest
from dataclasses import asdict
from types import SimpleNamespace

from src.user_answer_presenter import build_user_answer


def _call(tool_name: str, data: dict):
    return SimpleNamespace(
        tool_name=tool_name,
        result={
            "tool_name": tool_name,
            "data": data,
            "privacy": {
                "customer_id_values_exported": False,
                "public_customer_output": "aggregate_only",
            },
        },
    )


class UserAnswerPresenterTests(unittest.TestCase):
    def test_time_trend_leads_with_the_actual_month_and_value(self) -> None:
        answer = build_user_answer(
            [
                _call(
                    "analyze_time_trend",
                    {
                        "metric": "sales_amount_gbp",
                        "peak_period": "2011-11",
                        "peak_period_metrics": {
                            "month": "2011-11",
                            "sales_amount_gbp": "1503866.78",
                            "sales_quantity_items": 751377,
                            "order_count": 2769,
                        },
                        "excluded_incomplete_periods": ["2011-12"],
                    },
                )
            ]
        )
        self.assertEqual(
            answer.direct_answers[0],
            "销售额最高的完整月份是 **2011年11月**，当月销售额为 **£1,503,866.78**。",
        )
        self.assertIn("当月订单数：**2,769 笔**", answer.key_points)

    def test_product_ranking_uses_labels_and_a_readable_table(self) -> None:
        answer = build_user_answer(
            [
                _call(
                    "rank_products",
                    {
                        "metric": "sales_amount_gbp",
                        "ranking": [
                            {
                                "stock_code": "DOT",
                                "product_name": "DOTCOM POSTAGE",
                                "sales_amount_gbp": "206248.77",
                                "sales_quantity_items": 706,
                                "order_count": 706,
                            }
                        ],
                    },
                )
            ]
        )
        self.assertIn("DOTCOM POSTAGE", answer.direct_answers[0])
        self.assertEqual(answer.tables[0].rows[0]["销售额"], "£206,248.77")
        self.assertEqual(answer.tables[0].rows[0]["排名"], 1)

    def test_internal_fact_request_policy_and_privacy_markers_are_not_exposed(self) -> None:
        answer = build_user_answer(
            [
                _call(
                    "analyze_customers",
                    {
                        "customer_count": 4338,
                        "sales_row_coverage": 0.748067,
                        "sales_amount_coverage": 0.828881,
                        "sales_amount_gbp": "8811438.59",
                        "sales_quantity_items": 4747447,
                        "order_count": 18532,
                        "average_order_value_gbp": "475.47",
                        "privacy_note": "不展示原始 CustomerID [POLICY-001]",
                    },
                )
            ]
        )
        rendered = json.dumps(asdict(answer), ensure_ascii=False)
        for marker in ("FACT-", "REQUEST-", "POLICY-", "CustomerID"):
            self.assertNotIn(marker, rendered)

    def test_overview_and_customer_coverage_are_presented_as_two_named_scopes(self) -> None:
        answer = build_user_answer(
            [
                _call(
                    "get_sales_overview",
                    {
                        "sales_amount_gbp": "10642110.80",
                        "sales_quantity_items": 5572420,
                        "order_count": 19960,
                        "average_order_value_gbp": "533.17",
                    },
                ),
                _call(
                    "analyze_customers",
                    {
                        "customer_count": 4338,
                        "sales_row_coverage": 0.748067,
                        "sales_amount_coverage": 0.828881,
                        "sales_amount_gbp": "8811438.59",
                        "sales_quantity_items": 4747447,
                        "order_count": 18532,
                        "average_order_value_gbp": "475.47",
                        "privacy_note": "不展示原始 CustomerID",
                    },
                ),
            ]
        )
        self.assertIn("总体正常销售", answer.direct_answers[0])
        self.assertIn("已知客户子集", answer.direct_answers[1])
        self.assertIn("74.81%", answer.direct_answers[1])
        self.assertIn("82.89%", answer.direct_answers[1])
        self.assertEqual(answer.tables[0].rows[1]["客户数"], "4,338 位")
        rendered = json.dumps(asdict(answer), ensure_ascii=False)
        self.assertNotIn("CustomerID", rendered)


if __name__ == "__main__":
    unittest.main()
