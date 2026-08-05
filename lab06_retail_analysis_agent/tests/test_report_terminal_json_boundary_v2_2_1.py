from __future__ import annotations

import json
import unittest
from copy import deepcopy

from src.agent_protocol import AgentProtocolError, parse_control_response
from src.fixed_question_validation import (
    load_frozen_questions,
    validate_fixed_question,
)
from src.mock_h2_registry import FrozenH2MockRegistry
from src.mock_native_tool_client_v2_1_revision import (
    FrozenQuestionNativeToolMockClient,
)
from src.native_tool_transport_mock_v2_1_revision import (
    OfflineNativeToolTransportV2_1Revision,
)
from src.online_native_tool_candidate_v2_1_revision import (
    NativeToolOnlineCandidateV2_1Revision,
)
from src.report_terminal_json_boundary_v2_2_1 import (
    ReportTerminalJsonBoundaryError,
    load_report_terminal_json_boundary,
    validate_q01_q10_validation_coverage,
    validate_report_terminal_json_boundary,
)


class ReportTerminalJsonBoundaryV2_2_1Tests(unittest.TestCase):
    def test_contract_is_offline_q06_only_and_fail_closed(self) -> None:
        preflight = validate_report_terminal_json_boundary()
        self.assertEqual(preflight.model, "deepseek-v4-flash")
        self.assertEqual(preflight.question_ids, ("Q06",))
        self.assertEqual(
            preflight.tool_choice_sequence,
            ("auto", "auto", "none"),
        )
        self.assertEqual(
            preflight.response_formats,
            (None, None, {"type": "json_object"}),
        )
        self.assertFalse(preflight.dsml_extraction_allowed)
        self.assertFalse(preflight.real_model_calls_allowed)
        self.assertEqual(
            load_report_terminal_json_boundary()["status"],
            "frozen_by_user_pending_separate_real_authorization",
        )

    def test_contract_rejects_response_format_on_business_tool_step(self) -> None:
        changed = deepcopy(load_report_terminal_json_boundary())
        changed["candidate_protocol"]["response_2"][
            "response_format"
        ] = {"type": "json_object"}
        with self.assertRaises(ReportTerminalJsonBoundaryError):
            validate_report_terminal_json_boundary(changed)

    def test_coverage_does_not_claim_unrun_cases_passed(self) -> None:
        coverage = validate_q01_q10_validation_coverage()
        by_id = {
            item["question_id"]: item
            for item in coverage["questions"]
        }
        self.assertEqual(
            by_id["Q06"]["current_native_flash_real"],
            "failed",
        )
        for question_id, item in by_id.items():
            if question_id != "Q06":
                self.assertEqual(
                    item["current_native_flash_real"],
                    "not_run",
                )

    def test_q06_serializes_json_mode_only_on_third_request(self) -> None:
        transport = OfflineNativeToolTransportV2_1Revision(
            FrozenQuestionNativeToolMockClient(),
            q06_terminal_policy_enabled=True,
            q06_terminal_json_policy_enabled=True,
        )
        candidate = NativeToolOnlineCandidateV2_1Revision(
            api_key="offline-json-boundary-key",
            registry=FrozenH2MockRegistry(),
            response_limit=3,
            transport=transport,
            model="deepseek-v4-flash",
            q06_terminal_lock_enabled=True,
            q06_terminal_json_enabled=True,
        )
        outcome = candidate.run_turn(
            session_id="SESSION-v221-json",
            turn_id="TURN-006",
            question=load_frozen_questions()["Q06"]["question"],
            result_root="results/raw/v221_test_only",
        )

        self.assertEqual(outcome.status, "completed", outcome.error_message)
        self.assertEqual(
            validate_fixed_question("Q06", outcome).status,
            "protocol_and_dataflow_passed",
        )
        self.assertEqual(
            [request.tool_choice for request in transport.requests],
            ["auto", "auto", "none"],
        )
        self.assertEqual(
            [request.response_format for request in transport.requests],
            [None, None, {"type": "json_object"}],
        )
        self.assertTrue(
            all(request.tool_count == 7 for request in transport.requests)
        )
        self.assertEqual(
            [step.requested_response_format for step in candidate.last_trace],
            [None, None, {"type": "json_object"}],
        )

    def test_dsml_pseudo_tool_markup_is_not_repaired(self) -> None:
        dsml = (
            'Preface<||DSML||tool_calls><||DSML||invoke '
            'name="final_report">{"response_type":"report"}'
        )
        with self.assertRaisesRegex(
            AgentProtocolError,
            "不是有效JSON",
        ):
            parse_control_response(dsml)

    def test_valid_json_with_wrong_schema_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            AgentProtocolError,
            "不符合Agent控制Schema",
        ):
            parse_control_response(json.dumps({"response_type": "report"}))


if __name__ == "__main__":
    unittest.main()
