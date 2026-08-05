from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.claim_evidence_bundle_validation_v2_3_2 import (
    run_offline_validation,
)


class ClaimEvidenceBundleValidationV2_3_2Tests(unittest.TestCase):
    def test_formal_offline_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            summary = run_offline_validation(Path(temporary))
        self.assertEqual(summary["status"], "passed")
        self.assertEqual(summary["questions_passed"], 10)
        self.assertEqual(summary["total_model_responses"], 20)
        self.assertEqual(summary["q02_selection_limit_fact_id"], "FACT-001")
        self.assertEqual(summary["q06_cross_tool_dependency_bundle_count"], 1)
        self.assertTrue(all(summary["negative_probes"].values()))
        self.assertFalse(summary["program_authored_claim_text"])
        self.assertFalse(summary["post_hoc_report_repair"])
        self.assertFalse(summary["real_model_called"])


if __name__ == "__main__":
    unittest.main()
