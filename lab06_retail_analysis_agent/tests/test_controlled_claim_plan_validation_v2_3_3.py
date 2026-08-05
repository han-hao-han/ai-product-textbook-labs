from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.controlled_claim_plan_validation_v2_3_3 import run_offline_validation


class ControlledClaimPlanValidationV2_3_3Tests(unittest.TestCase):
    def test_formal_offline_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            summary = run_offline_validation(Path(temporary))
        self.assertEqual(summary["status"], "passed")
        self.assertEqual(summary["questions_passed"], 10)
        self.assertEqual(summary["q02_selection_limit_fact_id"], "FACT-001")
        self.assertFalse(summary["production_transport_integrated"])
        self.assertFalse(summary["real_model_called"])


if __name__ == "__main__":
    unittest.main()
