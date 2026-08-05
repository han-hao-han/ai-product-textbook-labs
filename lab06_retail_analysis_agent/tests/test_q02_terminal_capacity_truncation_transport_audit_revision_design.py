from __future__ import annotations

import unittest
from copy import deepcopy

from src.q02_terminal_capacity_truncation_transport_audit_revision_design import (
    Q02TerminalRevisionDesignError,
    build_transport_audit_candidate,
    classify_terminal_response_candidate,
    compile_q02_terminal_revision_preview,
    load_q02_terminal_revision_design,
    negative_probe_contracts,
    validate_q02_terminal_revision_design,
)


class Q02TerminalRevisionDesignTests(unittest.TestCase):
    def test_saved_response_is_classified_before_json_parse(self) -> None:
        preview = compile_q02_terminal_revision_preview()
        self.assertTrue(preview.passed)
        self.assertEqual(preview.observed_finish_reason, "length")
        self.assertEqual(preview.observed_completion_tokens, 4096)
        self.assertEqual(
            preview.proposed_primary_stop_code,
            "terminal_output_truncated",
        )

    def test_capacity_is_stage_specific_and_bounded(self) -> None:
        contract = validate_q02_terminal_revision_design()
        capacity = contract["boundary_1_terminal_output_capacity"]
        self.assertEqual(
            capacity["nonterminal_tool_selection_max_tokens"], 4096
        )
        self.assertEqual(capacity["report_terminal_max_tokens"], 8192)
        self.assertEqual(
            capacity["clarification_or_boundary_terminal_max_tokens"],
            4096,
        )
        self.assertFalse(capacity["unbounded_output_allowed"])

    def test_non_length_terminal_keeps_existing_parse_path(self) -> None:
        self.assertIsNone(
            classify_terminal_response_candidate(
                expected_terminal_response=True,
                finish_reason="stop",
            )
        )

    def test_truncation_short_circuits_downstream_dimensions(self) -> None:
        contract = validate_q02_terminal_revision_design()
        harness = contract["boundary_3_harness_short_circuit"]
        expected = "not_evaluated_due_to_terminal_output_truncation"
        self.assertEqual(harness["report_traceability_status"], expected)
        self.assertEqual(harness["report_completeness_status"], expected)
        self.assertEqual(harness["chart_acceptance_status"], expected)
        self.assertFalse(harness["q02_chart_count_mismatch_may_be_appended"])
        self.assertEqual(harness["overall_question_status"], "failed_stopped")

    def test_real_transport_audit_uses_authority_and_journal_counts(self) -> None:
        audit = build_transport_audit_candidate(
            execution_mode="real_transport",
            run_state={
                "attempted": 2,
                "http_responses_received": 2,
                "parsed_responses": 2,
                "failed_attempts": 0,
            },
        )
        self.assertEqual(audit["execution_mode"], "real_transport")
        self.assertTrue(audit["real_network_opened"])
        self.assertTrue(audit["real_model_response_received"])
        self.assertFalse(audit["api_key_value_saved"])
        self.assertFalse(audit["api_key_source_saved"])

    def test_offline_transport_remains_distinct(self) -> None:
        audit = build_transport_audit_candidate(
            execution_mode="offline_injected_transport",
            run_state={
                "attempted": 2,
                "http_responses_received": 2,
                "parsed_responses": 2,
                "failed_attempts": 0,
            },
        )
        self.assertFalse(audit["real_network_opened"])
        self.assertFalse(audit["real_model_response_received"])

    def test_unknown_transport_mode_is_rejected(self) -> None:
        with self.assertRaises(Q02TerminalRevisionDesignError):
            build_transport_audit_candidate(
                execution_mode="unknown",
                run_state={},
            )

    def test_nine_negative_scope_and_safety_probes_are_rejected(self) -> None:
        probes = negative_probe_contracts()
        self.assertEqual(len(probes), 9)
        for index, changed in enumerate(probes, start=1):
            with self.subTest(probe=index):
                with self.assertRaises(Q02TerminalRevisionDesignError):
                    validate_q02_terminal_revision_design(changed)

    def test_completed_design_keeps_all_future_permissions_closed(self) -> None:
        contract = validate_q02_terminal_revision_design()
        authority = contract["authorization"]
        self.assertFalse(authority["implementation_allowed"])
        self.assertFalse(authority["real_model_calls_allowed"])
        self.assertFalse(authority["batch_a_remaining_questions_authorized"])
        self.assertFalse(authority["batch_b_authorized"])
        self.assertFalse(authority["v2_2_3_may_resume"])

    def test_user_freeze_preserves_all_permission_gates(self) -> None:
        contract = validate_q02_terminal_revision_design()
        self.assertEqual(
            contract["status"],
            "frozen_by_user_offline_implementation_completed",
        )
        freeze = contract["user_freeze"]
        self.assertEqual(len(freeze["frozen_boundaries"]), 4)
        self.assertTrue(freeze["freeze_does_not_authorize_implementation"])
        self.assertTrue(freeze["freeze_does_not_authorize_real_model_calls"])
        self.assertTrue(freeze["batch_a_remaining_questions_not_authorized"])
        self.assertTrue(freeze["batch_b_not_authorized"])
        self.assertTrue(freeze["v2_2_3_remains_paused"])

    def test_incomplete_freeze_is_rejected(self) -> None:
        changed = deepcopy(load_q02_terminal_revision_design())
        changed["user_freeze"][
            "freeze_does_not_authorize_implementation"
        ] = False
        with self.assertRaises(Q02TerminalRevisionDesignError):
            validate_q02_terminal_revision_design(changed)

    def test_false_pass_or_retry_design_is_rejected(self) -> None:
        changed = deepcopy(load_q02_terminal_revision_design())
        changed["boundary_3_harness_short_circuit"][
            "overall_question_status"
        ] = "passed"
        with self.assertRaises(Q02TerminalRevisionDesignError):
            validate_q02_terminal_revision_design(changed)


if __name__ == "__main__":
    unittest.main()
