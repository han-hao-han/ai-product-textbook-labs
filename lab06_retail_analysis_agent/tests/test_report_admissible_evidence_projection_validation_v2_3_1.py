from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.report_admissible_evidence_projection_validation_v2_3_1 import (
    run_offline_validation,
    validate_design,
)


class ReportAdmissibleEvidenceValidationV2_3_1Tests(unittest.TestCase):
    def test_design_and_formal_offline_validation(self) -> None:
        self.assertEqual(
            validate_design()["selected_boundary"]["terminal_fact_shape"],
            "ReportFactReference",
        )
        with tempfile.TemporaryDirectory() as temporary:
            summary = run_offline_validation(Path(temporary))
        self.assertEqual(summary["status"], "passed")
        self.assertEqual(summary["questions_passed"], 10)
        self.assertEqual(summary["total_model_responses"], 20)
        self.assertFalse(summary["full_fact_objects_sent_to_terminal"])
        self.assertTrue(summary["report_reference_objects_sent_to_terminal"])
        self.assertFalse(
            summary["saved_q02_projection_probe"][
                "projected_contains_observed_value_524878"
            ]
        )
        self.assertTrue(
            summary["claim_local_negative_probe"][
                "rank_cannot_borrow_from_another_claim"
            ]
        )
        self.assertFalse(summary["real_model_called"])


if __name__ == "__main__":
    unittest.main()
