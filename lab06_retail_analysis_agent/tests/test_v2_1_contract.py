from __future__ import annotations

import json
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = (
    PROJECT_ROOT
    / "config"
    / "h3_tool_plan_semantic_support_v2_1_contract.json"
)
FAILED_V2_PATH = (
    PROJECT_ROOT / "config" / "h3_report_finalization_v2_contract.json"
)


class V2_1ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads(
            CONTRACT_PATH.read_text(encoding="utf-8")
        )
        cls.failed_v2 = json.loads(
            FAILED_V2_PATH.read_text(encoding="utf-8")
        )

    def test_v2_1_is_reopened_and_failed_v2_is_preserved(self) -> None:
        self.assertEqual(
            self.contract["status"],
            "reopened_by_user_for_mainline_correction",
        )
        self.assertEqual(self.contract["frozen_on"], "2026-07-31")
        self.assertEqual(self.contract["reopened_on"], "2026-07-31")
        self.assertEqual(
            self.failed_v2["status"],
            "frozen_by_user_real_validation_failed",
        )
        self.assertFalse(
            self.contract["authorization"][
                "real_model_calls_allowed"
            ]
        )
        self.assertFalse(
            self.contract["reopening"][
                "real_model_calls_allowed"
            ]
        )

    def test_q06_recipe_and_dependency_are_program_controlled(
        self,
    ) -> None:
        recipe = next(
            item
            for item in self.contract["recipe_registry"]
            if item["recipe_id"]
            == "peak_month_product_ranking"
        )

        self.assertEqual(
            recipe["tool_sequence"],
            ["analyze_time_trend", "rank_products"],
        )
        self.assertEqual(
            recipe["dependency"]["required_source_fact"][
                "metric"
            ],
            "peak_period",
        )
        self.assertFalse(
            self.contract["decision_boundary"][
                "model_may_select_tool_name_directly"
            ]
        )
        self.assertEqual(
            self.contract["status"],
            "reopened_by_user_for_mainline_correction",
        )

    def test_free_narrative_is_removed_from_semantic_plan(self) -> None:
        allowed = set(
            self.contract["semantic_report_boundary"][
                "model_output_allows"
            ]
        )
        forbidden = set(
            self.contract["semantic_report_boundary"][
                "model_output_forbids"
            ]
        )

        self.assertEqual(
            allowed,
            {"固定章节", "template_id", "当前轮fact_ids"},
        )
        self.assertIn("narrative", forbidden)
        self.assertEqual(
            self.contract["implementation"][
                "online_orchestrator_status"
            ],
            "not_wired_pending_user_freeze",
        )
        self.assertIn(
            "模型基于FACT组织报告",
            self.contract["reopening"]["scope"],
        )


if __name__ == "__main__":
    unittest.main()
