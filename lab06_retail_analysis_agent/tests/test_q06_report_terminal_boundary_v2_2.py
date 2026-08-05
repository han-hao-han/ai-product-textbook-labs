from __future__ import annotations

import unittest
from copy import deepcopy

from src.fixed_question_validation import (
    load_frozen_questions,
    validate_fixed_question,
)
from src.mock_h2_registry import FrozenH2MockRegistry
from src.native_tool_transport_mock_v2_1_revision import (
    OfflineNativeToolTransportV2_1Revision,
)
from src.online_native_tool_candidate_v2_1_revision import (
    NativeToolOnlineCandidateV2_1Revision,
)
from src.q06_report_terminal_boundary_mock import (
    Q06ReportTerminalConflictMockClient,
)
from src.q06_report_terminal_boundary_v2_2 import (
    Q06ReportTerminalBoundaryError,
    load_q06_report_terminal_boundary,
    validate_q06_report_terminal_boundary,
)


class Q06ReportTerminalBoundaryV2_2Tests(unittest.TestCase):
    def _run(self, *, terminal_lock: bool):
        transport = OfflineNativeToolTransportV2_1Revision(
            Q06ReportTerminalConflictMockClient(),
            q06_terminal_policy_enabled=terminal_lock,
        )
        candidate = NativeToolOnlineCandidateV2_1Revision(
            api_key="offline-terminal-boundary-key",
            registry=FrozenH2MockRegistry(),
            response_limit=3,
            transport=transport,
            model="deepseek-v4-flash",
            q06_terminal_lock_enabled=terminal_lock,
        )
        outcome = candidate.run_turn(
            session_id="SESSION-q06-terminal-boundary",
            turn_id="TURN-006",
            question=load_frozen_questions()["Q06"]["question"],
        )
        return outcome, candidate, transport

    def test_contract_preserves_mainline_and_has_no_real_authority(self) -> None:
        preflight = validate_q06_report_terminal_boundary()
        self.assertEqual(preflight.model, "deepseek-v4-flash")
        self.assertEqual(preflight.terminal_tool_choice, "none")
        self.assertEqual(preflight.tool_visibility, 7)
        self.assertFalse(preflight.real_model_calls_allowed)
        contract = load_q06_report_terminal_boundary()
        self.assertEqual(
            contract["status"],
            "frozen_by_user_pending_separate_real_authorization",
        )
        self.assertTrue(
            contract["user_freeze"][
                "freeze_does_not_authorize_real_calls"
            ]
        )

    def test_contract_rejects_program_generated_business_tool(self) -> None:
        changed = deepcopy(load_q06_report_terminal_boundary())
        changed["redesigned_protocol"]["terminal_trigger"][
            "program_may_synthesize_tool_or_arguments"
        ] = True
        with self.assertRaises(Q06ReportTerminalBoundaryError):
            validate_q06_report_terminal_boundary(changed)

    def test_legacy_auto_reproduces_extra_tool_failure(self) -> None:
        outcome, candidate, transport = self._run(terminal_lock=False)
        self.assertEqual(outcome.status, "failed")
        self.assertEqual(
            outcome.error_message,
            "Q06 does not allow another tool call",
        )
        self.assertEqual(len(outcome.tool_calls), 2)
        self.assertEqual(
            [request.tool_choice for request in transport.requests],
            ["auto", "auto", "auto"],
        )
        self.assertEqual(
            candidate.last_trace[2].selected_tool_name,
            "get_data_profile",
        )

    def test_terminal_none_completes_same_q06_without_extra_tool(self) -> None:
        outcome, candidate, transport = self._run(terminal_lock=True)
        self.assertEqual(outcome.status, "completed")
        self.assertEqual(
            validate_fixed_question("Q06", outcome).status,
            "protocol_and_dataflow_passed",
        )
        self.assertEqual(
            [request.tool_choice for request in transport.requests],
            ["auto", "auto", "none"],
        )
        self.assertEqual(
            [step.selected_tool_name for step in candidate.last_trace],
            ["analyze_time_trend", "rank_products", None],
        )
        self.assertEqual(len(outcome.tool_calls), 2)
        self.assertEqual(len(outcome.charts), 2)
        self.assertEqual(outcome.report_validation.status, "passed")


if __name__ == "__main__":
    unittest.main()
