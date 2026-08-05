from __future__ import annotations

import json
import unittest

from src.fixed_question_validation import (
    load_frozen_questions,
    validate_fixed_question,
)
from src.mock_h2_registry import FrozenH2MockRegistry
from src.mock_native_tool_client_v2_1_revision import (
    FrozenQuestionNativeToolMockClient,
)
from src.native_tool_transport_mock_v2_1_revision import (
    BETA_URL,
    OfflineNativeToolTransportV2_1Revision,
)
from src.online_native_tool_candidate_v2_1_revision import (
    NATIVE_REAL_MODEL_CONFIRMATION,
    NativeToolOnlineCandidateV2_1Revision,
    validate_native_real_authorization,
)
from scripts.validate_native_tool_online_transport_v2_1_revision import (
    ACCEPTED_OFFLINE_HARNESS_STATUSES,
    validate_request_contract,
)


class NativeToolOnlineTransportV2_1RevisionTests(unittest.TestCase):
    def test_q01_to_q10_cross_real_deepseek_request_serialization(self) -> None:
        questions = load_frozen_questions()
        transport = OfflineNativeToolTransportV2_1Revision(
            FrozenQuestionNativeToolMockClient()
        )
        candidate = NativeToolOnlineCandidateV2_1Revision(
            api_key="offline-placeholder-secret",
            registry=FrozenH2MockRegistry(),
            response_limit=20,
            transport=transport,
            question_count=10,
        )

        for index in range(1, 11):
            question_id = f"Q{index:02d}"
            outcome = candidate.run_turn(
                session_id="SESSION-native-transport",
                turn_id=f"TURN-{index:03d}",
                question=questions[question_id]["question"],
                result_root="results/raw/native_transport_test",
            )
            expected_status = (
                "protocol_and_dataflow_passed"
                if index <= 7
                else "passed_deterministic_pending_manual_review"
            )
            self.assertEqual(
                validate_fixed_question(question_id, outcome).status,
                expected_status,
            )

        snapshot = candidate.response_limit_snapshot()
        self.assertEqual(snapshot.limit, 20)
        self.assertEqual(snapshot.attempted, 20)
        self.assertEqual(snapshot.completed, 20)
        self.assertEqual(snapshot.failed, 0)
        self.assertEqual(len(transport.requests), 20)
        self.assertTrue(
            all(request.url == BETA_URL for request in transport.requests)
        )
        self.assertTrue(
            all(request.tool_count == 7 for request in transport.requests)
        )
        self.assertTrue(
            all(request.all_tools_strict for request in transport.requests)
        )
        self.assertTrue(
            all(
                request.all_parameters_closed
                for request in transport.requests
            )
        )
        self.assertEqual(
            sum(request.tool_choice == "none" for request in transport.requests),
            1,
        )
        self.assertEqual(
            sum(request.tool_choice == "auto" for request in transport.requests),
            19,
        )
        self.assertEqual(
            sum(request.max_tokens == 8192 for request in transport.requests),
            1,
        )
        self.assertEqual(
            sum(request.max_tokens == 4096 for request in transport.requests),
            19,
        )
        json_requests = [
            request
            for request in transport.requests
            if request.response_format_present
        ]
        self.assertEqual(len(json_requests), 1)
        self.assertEqual(json_requests[0].tool_choice, "none")
        self.assertEqual(
            json_requests[0].response_format,
            {"type": "json_object"},
        )
        self.assertEqual(
            ACCEPTED_OFFLINE_HARNESS_STATUSES,
            {
                "protocol_and_dataflow_passed",
                "passed_deterministic_pending_manual_review",
            },
        )
        self.assertTrue(
            validate_request_contract(
                transport.requests,
                q06_terminal_request_index=json_requests[0].request_index,
            )
        )

    def test_q06_requests_show_fact_dependent_message_progression(self) -> None:
        transport = OfflineNativeToolTransportV2_1Revision(
            FrozenQuestionNativeToolMockClient()
        )
        candidate = NativeToolOnlineCandidateV2_1Revision(
            api_key="offline-q06-placeholder",
            registry=FrozenH2MockRegistry(),
            response_limit=3,
            transport=transport,
        )
        outcome = candidate.run_turn(
            session_id="SESSION-native-transport-q06",
            turn_id="TURN-006",
            question=load_frozen_questions()["Q06"]["question"],
        )

        self.assertEqual(outcome.status, "completed")
        self.assertEqual(
            [request.tool_result_message_count for request in transport.requests],
            [0, 1, 2],
        )
        self.assertEqual(
            [request.tool_choice for request in transport.requests],
            ["auto", "auto", "none"],
        )
        self.assertEqual(
            [request.max_tokens for request in transport.requests],
            [4096, 4096, 8192],
        )
        self.assertEqual(
            [step.selected_tool_name for step in candidate.last_trace],
            ["analyze_time_trend", "rank_products", None],
        )
        self.assertEqual(
            outcome.tool_calls[1].arguments["start_date"],
            "2011-11-01",
        )

    def test_response_limit_stops_before_second_transport(self) -> None:
        transport = OfflineNativeToolTransportV2_1Revision(
            FrozenQuestionNativeToolMockClient()
        )
        candidate = NativeToolOnlineCandidateV2_1Revision(
            api_key="offline-limit-placeholder",
            registry=FrozenH2MockRegistry(),
            response_limit=1,
            transport=transport,
        )
        outcome = candidate.run_turn(
            session_id="SESSION-native-transport-limit",
            turn_id="TURN-001",
            question=load_frozen_questions()["Q01"]["question"],
        )

        self.assertEqual(outcome.status, "failed")
        self.assertEqual(outcome.error_stage, "model_response")
        self.assertEqual(len(outcome.tool_calls), 1)
        self.assertEqual(len(transport.requests), 1)
        self.assertEqual(
            candidate.response_limit_snapshot().attempted,
            1,
        )

    def test_transport_audit_does_not_save_secret_or_body(self) -> None:
        secret = "offline-secret-must-not-be-saved"
        transport = OfflineNativeToolTransportV2_1Revision(
            FrozenQuestionNativeToolMockClient()
        )
        candidate = NativeToolOnlineCandidateV2_1Revision(
            api_key=secret,
            registry=FrozenH2MockRegistry(),
            response_limit=1,
            transport=transport,
        )
        candidate.run_turn(
            session_id="SESSION-native-transport-audit",
            turn_id="TURN-008",
            question=load_frozen_questions()["Q08"]["question"],
        )

        audit_text = json.dumps(transport.audit_payload())
        self.assertNotIn(secret, audit_text)
        self.assertNotIn(f"Bearer {secret}", audit_text)
        self.assertIn('"authorization_value_saved": false', audit_text)
        self.assertIn('"request_body_saved": false', audit_text)

    def test_real_network_requires_new_exact_confirmation(self) -> None:
        with self.assertRaises(ValueError):
            NativeToolOnlineCandidateV2_1Revision(
                api_key="not-used",
                registry=FrozenH2MockRegistry(),
                response_limit=1,
            )
        with self.assertRaises(ValueError):
            validate_native_real_authorization(
                confirmation=NATIVE_REAL_MODEL_CONFIRMATION,
                approved_model_responses=5,
                question_count=1,
            )
        validate_native_real_authorization(
            confirmation=NATIVE_REAL_MODEL_CONFIRMATION,
            approved_model_responses=4,
            question_count=1,
        )


if __name__ == "__main__":
    unittest.main()
