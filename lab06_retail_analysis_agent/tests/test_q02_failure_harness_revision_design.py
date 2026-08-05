from __future__ import annotations

import unittest
from copy import deepcopy

from src.q02_failure_harness_revision_design import (
    EXPECTED_ROOT_CODES,
    Q02FailureHarnessRevisionDesignError,
    compile_q02_failure_harness_design_preview,
    load_q02_failure_harness_revision_design,
    validate_q02_failure_harness_revision_design,
)


class Q02FailureHarnessRevisionDesignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.preview = compile_q02_failure_harness_design_preview()

    def test_real_root_failures_remain_unchanged(self) -> None:
        self.assertEqual(
            list(self.preview.root_failure_codes),
            EXPECTED_ROOT_CODES,
        )

    def test_retention_and_request_mapping_explain_manifest_counts(self) -> None:
        self.assertEqual(
            (self.preview.current_manifest_total, self.preview.current_manifest_covered),
            (27, 0),
        )
        self.assertEqual(
            (self.preview.retained_manifest_total, self.preview.retained_manifest_covered),
            (27, 26),
        )
        self.assertTrue(self.preview.candidate_metric_mapping_covered)
        self.assertEqual(
            (self.preview.candidate_manifest_total, self.preview.candidate_manifest_covered),
            (27, 27),
        )

    def test_saved_chart_request_is_buildable_but_not_accepted(self) -> None:
        self.assertEqual(self.preview.saved_chart_requests, 1)
        self.assertEqual(self.preview.buildable_saved_charts, 1)
        contract = validate_q02_failure_harness_revision_design()
        expected = contract["expected_q02_state_after_future_implementation"]
        self.assertEqual(expected["overall_status"], "failed_stopped")
        self.assertFalse(expected["real_model_result_changed_to_pass"])

    def test_root_priority_replaces_generic_first_failure(self) -> None:
        self.assertEqual(
            self.preview.current_stop_reason,
            "unexpected_terminal_status",
        )
        self.assertEqual(
            self.preview.candidate_primary_stop_stage,
            "report_validation",
        )

    def test_design_is_offline_only_and_does_not_change_sources(self) -> None:
        self.assertTrue(self.preview.source_files_unchanged)
        self.assertFalse(self.preview.implementation_performed)
        self.assertFalse(self.preview.real_model_called)
        self.assertFalse(self.preview.network_used)
        self.assertFalse(self.preview.api_key_read)

    def test_contract_rejects_scope_or_authority_expansion(self) -> None:
        for section, field in (
            ("scope", "implementation_performed"),
            ("scope", "prompt_changed"),
            ("scope", "average_value_rule_changed"),
            ("scope", "real_model_calls_allowed"),
            ("authorization", "implementation_allowed"),
        ):
            changed = deepcopy(
                load_q02_failure_harness_revision_design()
            )
            changed[section][field] = True
            with self.subTest(section=section, field=field):
                with self.assertRaises(
                    Q02FailureHarnessRevisionDesignError
                ):
                    validate_q02_failure_harness_revision_design(changed)

    def test_contract_rejects_false_pass_or_relaxed_evidence(self) -> None:
        probes = []
        passed = deepcopy(load_q02_failure_harness_revision_design())
        passed["expected_q02_state_after_future_implementation"][
            "real_model_result_changed_to_pass"
        ] = True
        probes.append(passed)
        fuzzy = deepcopy(load_q02_failure_harness_revision_design())
        fuzzy["boundary_3_request_display_mapping"][
            "fuzzy_matching_allowed"
        ] = True
        probes.append(fuzzy)
        not_evaluated = deepcopy(
            load_q02_failure_harness_revision_design()
        )
        not_evaluated["boundary_2_upstream_failure_short_circuit"][
            "not_evaluated_is_not_passed"
        ] = False
        probes.append(not_evaluated)
        publishable = deepcopy(
            load_q02_failure_harness_revision_design()
        )
        publishable["boundary_1_rejected_report_evidence"][
            "publishable"
        ] = True
        probes.append(publishable)
        for index, changed in enumerate(probes, start=1):
            with self.subTest(probe=index):
                with self.assertRaises(
                    Q02FailureHarnessRevisionDesignError
                ):
                    validate_q02_failure_harness_revision_design(changed)

    def test_user_freeze_does_not_authorize_implementation_or_real_calls(self) -> None:
        contract = validate_q02_failure_harness_revision_design()
        self.assertEqual(
            contract["status"],
            "frozen_by_user_offline_validated_not_implemented",
        )
        freeze = contract["user_freeze"]
        self.assertEqual(len(freeze["frozen_boundaries"]), 4)
        self.assertTrue(
            freeze["freeze_does_not_authorize_implementation"]
        )
        self.assertTrue(
            freeze["freeze_does_not_authorize_real_model_calls"]
        )
        self.assertTrue(
            freeze["batch_a_remaining_questions_not_authorized"]
        )
        self.assertTrue(freeze["v2_2_3_remains_paused"])


if __name__ == "__main__":
    unittest.main()
