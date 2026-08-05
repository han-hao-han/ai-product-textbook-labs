from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.controlled_claim_plan_transport_validation_v2_3_3 import run_offline_validation


class ControlledClaimPlanTransportValidationV2_3_3Tests(unittest.TestCase):
    def test_formal_integrated_offline_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            summary = run_offline_validation(Path(temporary))
        self.assertEqual(summary["status"], "passed")
        self.assertEqual(summary["questions_passed"], 10)
        self.assertEqual(summary["total_counted_model_responses"], 27)
        self.assertTrue(summary["invalid_plan_stops_before_final_report"])
        self.assertFalse(summary["real_model_called"])


if __name__ == "__main__":
    unittest.main()
