from __future__ import annotations

import unittest

from src.native_report_prompt_evidence_guard_design import (
    NativeReportPromptEvidenceGuardDesignError,
    load_native_report_prompt_evidence_guard_design,
    validate_native_report_prompt_evidence_guard_design,
)


class NativeReportPromptEvidenceGuardDesignTests(unittest.TestCase):
    def test_candidate_targets_all_saved_root_failures(self) -> None:
        result = validate_native_report_prompt_evidence_guard_design()
        self.assertTrue(result.passed)
        self.assertEqual(result.targeted_root_issue_count, 3)
        self.assertEqual(result.root_issue_count, 3)
        self.assertEqual(
            result.rule_ids,
            (
                "PROMPT-EVIDENCE-01",
                "PROMPT-EVIDENCE-02",
                "PROMPT-EVIDENCE-03",
            ),
        )

    def test_candidate_is_generic_and_does_not_edit_active_prompt(self) -> None:
        result = validate_native_report_prompt_evidence_guard_design()
        self.assertTrue(all(result.negative_probes.values()))
        self.assertEqual(result.q01_q10_offline_status, "passed")

    def test_scope_widening_is_rejected(self) -> None:
        contract = load_native_report_prompt_evidence_guard_design()
        contract["scope"]["modify_acceptance_root_rules"] = True
        with self.assertRaises(NativeReportPromptEvidenceGuardDesignError):
            validate_native_report_prompt_evidence_guard_design(contract)

    def test_q02_hardcoding_is_rejected(self) -> None:
        contract = load_native_report_prompt_evidence_guard_design()
        contract["candidate_additive_rules"][0]["text"] += " Q02"
        with self.assertRaises(NativeReportPromptEvidenceGuardDesignError):
            validate_native_report_prompt_evidence_guard_design(contract)


if __name__ == "__main__":
    unittest.main()
