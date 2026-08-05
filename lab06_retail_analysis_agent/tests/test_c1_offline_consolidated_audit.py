from __future__ import annotations

import unittest

from src.c1_offline_consolidated_audit import (
    C1OfflineConsolidatedAuditError,
    load_c1_offline_consolidated_audit_contract,
    run_c1_offline_consolidated_audit,
)


class C1OfflineConsolidatedAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = run_c1_offline_consolidated_audit()

    def test_three_offline_evidence_chains_pass(self) -> None:
        self.assertTrue(self.result.passed)
        self.assertEqual(
            self.result.q02_summary["primary_stop_stage"],
            "report_validation",
        )
        self.assertEqual(self.result.q01_q10_summary["status"], "passed")
        self.assertEqual(self.result.batch_a_summary["status"], "passed")

    def test_q02_root_failure_and_harness_consequence_are_separate(self) -> None:
        findings = {item["id"]: item for item in self.result.findings}
        self.assertEqual(findings["C1-F01"]["status"], "resolved")
        self.assertEqual(findings["C1-F02"]["status"], "open_decision")
        self.assertFalse(
            self.result.q02_summary["q02_chart_count_mismatch_present"]
        )

    def test_frozen_sources_match_recorded_hashes(self) -> None:
        self.assertEqual(len(self.result.frozen_hashes), 9)
        self.assertIn(
            "prompts/native_tool_report_v2_1_revision.md",
            self.result.frozen_hashes,
        )

    def test_authority_widening_is_rejected(self) -> None:
        contract = load_c1_offline_consolidated_audit_contract()
        contract["authorization"]["real_model_calls_allowed"] = True
        with self.assertRaises(C1OfflineConsolidatedAuditError):
            run_c1_offline_consolidated_audit(contract)


if __name__ == "__main__":
    unittest.main()
