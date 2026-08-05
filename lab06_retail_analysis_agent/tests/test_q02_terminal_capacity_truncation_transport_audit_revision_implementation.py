from __future__ import annotations

import unittest

from src.q02_terminal_capacity_truncation_transport_audit_revision_implementation import (
    NOT_EVALUATED,
    compile_q02_terminal_revision_implementation,
)


class Q02TerminalRevisionImplementationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = compile_q02_terminal_revision_implementation()

    def test_saved_real_response_is_failed_before_json_parse(self) -> None:
        self.assertTrue(self.result.passed)
        self.assertEqual(self.result.direct_outcome_status, "failed")
        self.assertEqual(self.result.direct_error_stage, "model_response")
        self.assertEqual(
            self.result.direct_error_message,
            "模型终态响应达到输出上限，JSON可能不完整",
        )
        self.assertEqual(self.result.direct_response_count, 2)

    def test_tool_result_remains_independently_correct(self) -> None:
        self.assertEqual(self.result.direct_tool_names, ("rank_products",))
        self.assertEqual(self.result.tool_reference_answer_status, "passed")

    def test_harness_short_circuits_all_report_dimensions(self) -> None:
        self.assertEqual(
            self.result.report_content_acceptance_status,
            NOT_EVALUATED,
        )
        self.assertEqual(
            self.result.batch_evaluation_states,
            {
                "report_traceability": NOT_EVALUATED,
                "report_completeness": NOT_EVALUATED,
                "chart_acceptance": NOT_EVALUATED,
            },
        )
        self.assertNotIn(
            "q02_chart_count_mismatch",
            self.result.batch_program_failures,
        )

    def test_root_code_precedes_acceptance_consequence(self) -> None:
        self.assertEqual(
            self.result.batch_primary_stop_codes,
            ("terminal_output_truncated",),
        )
        self.assertEqual(
            self.result.batch_primary_stop_stage,
            "model_response",
        )
        self.assertEqual(
            self.result.batch_acceptance_consequences,
            ("new_harness_deterministic_acceptance_failed",),
        )

    def test_capacity_and_transport_audit_match_frozen_design(self) -> None:
        self.assertEqual(self.result.request_max_tokens, (4096, 8192))
        self.assertEqual(
            self.result.offline_transport_audit["execution_mode"],
            "offline_injected_transport",
        )
        real = self.result.saved_real_transport_audit_preview
        self.assertEqual(real["execution_mode"], "real_transport")
        self.assertEqual(
            (
                real["attempted"],
                real["http_responses_received"],
                real["parsed_responses"],
                real["failed_attempts"],
            ),
            (2, 2, 2, 0),
        )
        self.assertFalse(real["api_key_value_saved"])
        self.assertFalse(real["api_key_source_saved"])

    def test_replay_is_strictly_offline(self) -> None:
        self.assertFalse(self.result.real_model_called)
        self.assertFalse(self.result.network_used)
        self.assertFalse(self.result.api_key_read)


if __name__ == "__main__":
    unittest.main()
