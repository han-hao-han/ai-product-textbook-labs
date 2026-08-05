from __future__ import annotations

import unittest

from src.claim_local_evidence_bundle_design_v2_3_2 import validate_design


class ClaimLocalEvidenceBundleDesignV2_3_2Tests(unittest.TestCase):
    def test_offline_design_preserves_mainline_and_frozen_boundaries(self) -> None:
        audit = validate_design()
        self.assertEqual(audit.status, "passed")
        self.assertTrue(audit.frozen_source_hashes_match)
        self.assertTrue(audit.real_q02_root_cause_matches)
        self.assertTrue(audit.generic_grouping_only)
        self.assertTrue(audit.model_report_responsibility_preserved)
        self.assertTrue(audit.claim_local_validator_preserved)
        self.assertTrue(audit.q02_selection_limit_dependency_distinguished)
        self.assertTrue(audit.implementation_authorized)
        self.assertFalse(audit.real_model_called)


if __name__ == "__main__":
    unittest.main()
