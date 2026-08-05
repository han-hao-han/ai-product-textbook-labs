from __future__ import annotations

import unittest

from src.q02_terminal_revision_concentrated_audit import (
    Q02TerminalRevisionConcentratedAuditError,
    negative_audit_contracts,
    validate_q02_terminal_revision_implementation_contract,
)


class Q02TerminalRevisionConcentratedAuditTests(unittest.TestCase):
    def test_all_offline_evidence_and_hashes_pass(self) -> None:
        result = validate_q02_terminal_revision_implementation_contract()
        self.assertTrue(result.passed)
        self.assertTrue(result.implementation_hashes_match)
        self.assertTrue(result.frozen_hashes_match)
        self.assertTrue(all(result.evidence_checks.values()))
        self.assertEqual(result.q02_root_code, "terminal_output_truncated")
        self.assertEqual(result.q01_q10_mock_passed, 10)
        self.assertEqual(result.q01_q10_transport_passed, 10)
        self.assertEqual(result.harness_negative_probes_passed, 9)
        self.assertEqual(result.batch_a_offline_status, "passed")

    def test_five_boundary_and_drift_probes_are_rejected(self) -> None:
        probes = negative_audit_contracts()
        self.assertEqual(len(probes), 5)
        for index, probe in enumerate(probes, start=1):
            with self.subTest(probe=index):
                with self.assertRaises(
                    Q02TerminalRevisionConcentratedAuditError
                ):
                    validate_q02_terminal_revision_implementation_contract(
                        probe
                    )


if __name__ == "__main__":
    unittest.main()
