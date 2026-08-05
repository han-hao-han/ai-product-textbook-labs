from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.export_fact_chart_report_contract import build_contract


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = (
    PROJECT_ROOT
    / "config"
    / "h3_fact_chart_report_contract.json"
)


class FactChartReportContractTests(unittest.TestCase):
    def test_checked_in_contract_matches_schema_source(self) -> None:
        checked_in = json.loads(
            CONTRACT_PATH.read_text(encoding="utf-8")
        )

        self.assertEqual(checked_in, build_contract())

    def test_frozen_contract_keeps_model_away_from_calculation_and_code(
        self,
    ) -> None:
        contract = build_contract()

        self.assertEqual(contract["status"], "frozen_by_user")
        self.assertFalse(
            contract["fact"]["value_policy"][
                "model_may_calculate_or_convert"
            ]
        )
        self.assertFalse(
            contract["chart_data"][
                "model_generated_chart_code_allowed"
            ]
        )
        self.assertTrue(contract["chart_data"]["single_call_only"])
        extension = contract["v2_2_2_additive_extension"]
        self.assertTrue(
            extension[
                "report_validation_result_adds_manual_review_flags"
            ]
        )
        self.assertFalse(
            extension["manual_flags_change_deterministic_status"]
        )
        self.assertFalse(extension["report_draft_schema_changed"])
        self.assertFalse(extension["fact_schema_changed"])


if __name__ == "__main__":
    unittest.main()
