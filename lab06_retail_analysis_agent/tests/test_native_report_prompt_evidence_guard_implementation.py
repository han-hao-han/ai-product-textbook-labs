from __future__ import annotations

import unittest

from src.native_report_prompt_evidence_guard_implementation import (
    NativeReportPromptEvidenceGuardImplementationError,
    load_native_report_prompt_evidence_guard_implementation,
    validate_native_report_prompt_evidence_guard_implementation,
)


class NativeReportPromptEvidenceGuardImplementationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = (
            validate_native_report_prompt_evidence_guard_implementation()
        )

    def test_new_prompt_is_wired_and_contains_all_guards(self) -> None:
        self.assertTrue(self.result.passed)
        self.assertEqual(
            self.result.prompt_version,
            "1.5.6-h3-native-tool-report-evidence-guard-v1",
        )
        self.assertTrue(self.result.runtime_prompt_contains_all_guards)

    def test_saved_q02_failure_is_preserved(self) -> None:
        self.assertEqual(self.result.saved_q02_status, "failed_stopped")
        self.assertEqual(
            self.result.saved_q02_tool_reference_answer_status, "passed"
        )
        self.assertEqual(
            self.result.saved_q02_root_failure_codes,
            (
                "untraceable_numeric_token",
                "unsupported_average_value_claim",
                "unsupported_average_value_claim",
            ),
        )

    def test_q01_q10_offline_regression_passes(self) -> None:
        self.assertEqual(self.result.q01_q10_passed, 10)
        self.assertEqual(self.result.q01_q10_total, 10)
        self.assertEqual(
            set(self.result.q01_q10_statuses.values()),
            {
                "protocol_and_dataflow_passed",
                "passed_deterministic_pending_manual_review",
            },
        )

    def test_frozen_sources_remain_unchanged(self) -> None:
        self.assertEqual(len(self.result.frozen_hashes), 11)

    def test_authority_widening_is_rejected(self) -> None:
        contract = load_native_report_prompt_evidence_guard_implementation()
        contract["authorization"]["real_model_calls_allowed"] = True
        with self.assertRaises(
            NativeReportPromptEvidenceGuardImplementationError
        ):
            validate_native_report_prompt_evidence_guard_implementation(
                contract
            )


if __name__ == "__main__":
    unittest.main()
