from __future__ import annotations

import unittest
from copy import deepcopy

from src.q01_q10_acceptance_harness_audit import (
    AcceptanceHarnessAuditError,
    load_acceptance_harness_audit_contract,
    run_acceptance_harness_audit,
    validate_acceptance_harness_audit_contract,
)


class Q01Q10AcceptanceHarnessAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = run_acceptance_harness_audit()
        cls.by_id = {
            item.question_id: item for item in cls.result.questions
        }

    def test_all_mock_fixed_validations_pass_but_reports_are_incomplete(
        self,
    ) -> None:
        self.assertTrue(
            all(
                item.mock_fixed_validation_status == "passed"
                for item in self.result.questions
            )
        )
        incomplete = {
            item.question_id
            for item in self.result.questions
            if item.report_required
            and item.report_reference_coverage_ratio != 1.0
        }
        self.assertEqual(
            incomplete,
            {"Q01", "Q02", "Q03", "Q04", "Q05", "Q06", "Q07"},
        )

    def test_rank_propagation_finding_is_now_remediated(self) -> None:
        self.assertEqual(
            self.by_id["Q02"].non_selected_metric_rank_fact_count,
            0,
        )
        self.assertEqual(
            self.by_id["Q03"].non_selected_metric_rank_fact_count,
            0,
        )
        self.assertEqual(
            self.by_id["Q06"].non_selected_metric_rank_fact_count,
            0,
        )

    def test_request_numeric_provenance_is_missing_for_four_reports(
        self,
    ) -> None:
        missing = {
            item.question_id
            for item in self.result.questions
            if item.report_required
            and not item.request_numeric_source_type_supported
        }
        self.assertEqual(missing, {"Q02", "Q03", "Q04", "Q06"})

    def test_unchecked_control_text_probes_still_pass_fixed_validation(
        self,
    ) -> None:
        self.assertTrue(all(self.result.control_text_probes.values()))

    def test_audit_is_read_only_and_has_no_real_authority(self) -> None:
        contract = validate_acceptance_harness_audit_contract()
        self.assertEqual(
            contract["status"],
            "findings_accepted_six_boundaries_reopened_offline_design",
        )
        self.assertEqual(contract["offline_audit"]["finding_count"], 7)
        self.assertEqual(
            len(contract["user_decision"]["reopened_boundaries"]),
            6,
        )
        self.assertTrue(
            contract["user_decision"][
                "h2_reference_answers_must_not_change"
            ]
        )
        self.assertEqual(self.result.status, "findings_confirmed")
        self.assertTrue(self.result.source_files_unchanged)
        self.assertFalse(self.result.real_model_called)
        self.assertFalse(self.result.network_used)
        self.assertFalse(self.result.api_key_read)

    def test_contract_rejects_validator_change_or_v2_2_3_resume(self) -> None:
        validate_acceptance_harness_audit_contract()
        validator = deepcopy(load_acceptance_harness_audit_contract())
        validator["scope"]["validation_rules_changed"] = True
        with self.assertRaises(AcceptanceHarnessAuditError):
            validate_acceptance_harness_audit_contract(validator)

        resumed = deepcopy(load_acceptance_harness_audit_contract())
        resumed["scope"]["v2_2_3_resumed"] = True
        with self.assertRaises(AcceptanceHarnessAuditError):
            validate_acceptance_harness_audit_contract(resumed)


if __name__ == "__main__":
    unittest.main()
