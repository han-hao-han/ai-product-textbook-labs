from __future__ import annotations

import json
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
V1_CONTRACT = (
    PROJECT_ROOT / "config" / "h3_fact_chart_report_contract.json"
)
V2_CONTRACT = (
    PROJECT_ROOT
    / "config"
    / "h3_report_finalization_v2_contract.json"
)


class ReportFinalizationV2ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.v1 = json.loads(V1_CONTRACT.read_text(encoding="utf-8"))
        cls.v2 = json.loads(V2_CONTRACT.read_text(encoding="utf-8"))

    def test_v1_remains_frozen_and_v2_records_failed_real_validation(
        self,
    ) -> None:
        self.assertEqual(self.v1["status"], "frozen_by_user")
        self.assertEqual(
            self.v2["status"],
            "frozen_by_user_real_validation_failed",
        )
        self.assertEqual(
            self.v2["supersession"]["v1_status"],
            "frozen_and_unchanged",
        )
        self.assertTrue(
            self.v2["frozen_dependencies"][
                "seven_tool_names_unchanged"
            ]
        )

    def test_four_phase_boundary_and_endpoints_are_explicit(self) -> None:
        phases = self.v2["v2_pipeline"]
        self.assertEqual(
            [phase["phase"] for phase in phases],
            [
                "decision_gate",
                "strict_tool_execution",
                "report_plan",
                "program_finalization",
            ],
        )
        self.assertEqual(
            phases[0]["response_mode"],
            {"type": "json_object"},
        )
        self.assertIn("/beta/", phases[1]["model_endpoint"])
        self.assertIn(
            "value",
            phases[2]["model_input_fact_catalog_excludes"],
        )
        self.assertFalse(phases[3]["model_called"])

    def test_real_validation_failure_cannot_be_reported_as_passed(
        self,
    ) -> None:
        self.assertFalse(
            self.v2["offline_validation"]["real_model_called"]
        )
        self.assertEqual(
            self.v2["real_model_validation"]["status"],
            "completed_with_q06_failure",
        )
        self.assertTrue(
            self.v2["real_model_validation"][
                "new_authorization_required"
            ]
        )
        self.assertEqual(
            self.v2["model_response_count"][
                "q06_two_tool_analysis"
            ],
            4,
        )
        self.assertEqual(
            self.v2["real_model_validation"]["passed"],
            2,
        )
        self.assertEqual(
            self.v2["real_model_validation"]["failed"],
            1,
        )


if __name__ == "__main__":
    unittest.main()
