from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import run_v2_1_online_candidate
from src.agent_orchestrator_v2_1 import (
    RetailAgentOrchestratorV2_1,
)
from src.deepseek_client import (
    DeepSeekChatClient,
    DeepSeekClientError,
    HttpResponseData,
)
from src.deepseek_transport_mock_v2_1 import (
    BETA_URL,
    STANDARD_URL,
    OfflineDeepSeekTransportV2_1,
)
from src.fixed_question_validation import (
    load_frozen_questions,
    validate_fixed_question,
)
from src.mock_h2_registry import FrozenH2MockRegistry
from src.mock_v2_1_client import FrozenQuestionV2_1MockClient
from src.online_candidate_v2_1 import (
    REAL_MODEL_CONFIRMATION_V2_1,
    ResponseLimitedClientV2_1,
    validate_real_model_authorization_v2_1,
)


class FailingProviderClient:
    def complete_json(self, *, messages):
        raise DeepSeekClientError("offline transport failure")

    def complete_strict_tools(self, *, messages, tools):
        raise DeepSeekClientError("offline transport failure")


class V2_1OnlineCandidateTransportTests(unittest.TestCase):
    def test_technical_candidate_records_offline_not_real_validation(
        self,
    ) -> None:
        project_root = Path(__file__).resolve().parents[1]
        candidate = json.loads(
            (
                project_root
                / "config"
                / "h3_technical_contract.candidate.json"
            ).read_text(encoding="utf-8")
        )
        validation = candidate[
            "tool_plan_semantic_support_v2_1_candidate"
        ]["online_candidate_transport"]

        self.assertEqual(
            validation["status"],
            "wired_and_offline_transport_validated",
        )
        self.assertFalse(validation["real_network_opened"])
        self.assertFalse(validation["real_model_called"])
        self.assertTrue(
            validation[
                "real_model_calls_require_new_user_authorization"
            ]
        )

    def test_q01_to_q10_cross_real_request_serialization(self) -> None:
        questions = load_frozen_questions()
        transport = OfflineDeepSeekTransportV2_1(
            FrozenQuestionV2_1MockClient()
        )
        client = ResponseLimitedClientV2_1(
            DeepSeekChatClient(
                api_key="test-placeholder-secret",
                transport=transport,
            ),
            limit=27,
        )
        orchestrator = RetailAgentOrchestratorV2_1(
            client=client,
            registry=FrozenH2MockRegistry(),
        )

        for index in range(1, 11):
            question_id = f"Q{index:02d}"
            outcome = orchestrator.run_turn(
                session_id="SESSION-TRANSPORT",
                turn_id=f"TURN-{index:03d}",
                question=questions[question_id]["question"],
                result_root="results/raw/offline_transport_test",
            )
            self.assertEqual(
                validate_fixed_question(
                    question_id,
                    outcome,
                ).status,
                "passed",
            )

        snapshot = client.snapshot()
        self.assertEqual(snapshot.limit, 27)
        self.assertEqual(snapshot.attempted, 27)
        self.assertEqual(snapshot.completed, 27)
        self.assertEqual(snapshot.failed, 0)
        self.assertEqual(len(transport.requests), 27)
        self.assertEqual(
            sum(
                request.endpoint_kind == "standard_json"
                for request in transport.requests
            ),
            17,
        )
        self.assertEqual(
            sum(
                request.endpoint_kind == "beta_strict_tool"
                for request in transport.requests
            ),
            10,
        )
        self.assertTrue(
            all(
                request.url
                in {
                    STANDARD_URL,
                    BETA_URL,
                }
                for request in transport.requests
            )
        )

    def test_transport_audit_never_saves_authorization_value(self) -> None:
        transport = OfflineDeepSeekTransportV2_1(
            FrozenQuestionV2_1MockClient()
        )
        questions = load_frozen_questions()
        client = DeepSeekChatClient(
            api_key="audit-secret-must-not-be-saved",
            transport=transport,
        )
        RetailAgentOrchestratorV2_1(
            client=client,
            registry=FrozenH2MockRegistry(),
        ).run_turn(
            session_id="SESSION-AUDIT",
            turn_id="TURN-001",
            question=questions["Q08"]["question"],
        )

        audit_text = json.dumps(
            transport.audit_payload(),
            ensure_ascii=False,
        )
        self.assertNotIn(
            "audit-secret-must-not-be-saved",
            audit_text,
        )
        self.assertNotIn("Bearer audit-secret", audit_text)
        self.assertIn('"authorization_value_saved": false', audit_text)
        self.assertIn('"request_body_saved": false', audit_text)

    def test_response_limit_is_reserved_before_failed_transport(self) -> None:
        client = ResponseLimitedClientV2_1(
            FailingProviderClient(),
            limit=1,
        )

        with self.assertRaises(DeepSeekClientError):
            client.complete_json(messages=[])
        snapshot = client.snapshot()
        self.assertEqual(snapshot.attempted, 1)
        self.assertEqual(snapshot.completed, 0)
        self.assertEqual(snapshot.failed, 1)
        with self.assertRaises(DeepSeekClientError):
            client.complete_json(messages=[])
        self.assertEqual(client.snapshot(), snapshot)

    def test_http_error_becomes_decision_stage_failure(self) -> None:
        def transport(url, body, headers, timeout):
            return HttpResponseData(
                status_code=429,
                content=json.dumps(
                    {
                        "error": {
                            "type": "rate_limit_error",
                        }
                    }
                ).encode("utf-8"),
            )

        client = ResponseLimitedClientV2_1(
            DeepSeekChatClient(
                api_key="test-only",
                transport=transport,
            ),
            limit=1,
        )
        outcome = RetailAgentOrchestratorV2_1(
            client=client,
            registry=FrozenH2MockRegistry(),
        ).run_turn(
            session_id="SESSION-ERROR",
            turn_id="TURN-001",
            question="查看销售概览",
        )

        self.assertEqual(outcome.status, "failed")
        self.assertEqual(outcome.error_stage, "decision")
        self.assertIn("HTTP 429", outcome.error_message)
        self.assertEqual(outcome.raw_responses, ())
        self.assertEqual(client.snapshot().attempted, 1)
        self.assertEqual(client.snapshot().failed, 1)

    def test_real_runner_requires_exact_confirmation_and_safe_cap(
        self,
    ) -> None:
        with self.assertRaises(ValueError):
            validate_real_model_authorization_v2_1(
                confirmation="",
                approved_model_responses=1,
                question_count=1,
            )
        with self.assertRaises(ValueError):
            validate_real_model_authorization_v2_1(
                confirmation=REAL_MODEL_CONFIRMATION_V2_1,
                approved_model_responses=5,
                question_count=1,
            )
        validate_real_model_authorization_v2_1(
            confirmation=REAL_MODEL_CONFIRMATION_V2_1,
            approved_model_responses=4,
            question_count=1,
        )

    def test_retired_recipe_entry_stops_before_key_even_with_old_confirmation(
        self,
    ) -> None:
        arguments = [
            "run_v2_1_online_candidate.py",
            "--question-ids",
            "Q06",
            "--approved-model-responses",
            "4",
            "--confirm-real-model-calls",
            REAL_MODEL_CONFIRMATION_V2_1,
        ]
        with (
            patch("sys.argv", arguments),
            patch.object(
                run_v2_1_online_candidate,
                "_load_dotenv_value",
                side_effect=AssertionError(
                    "未授权时不应读取.env"
                ),
            ),
            self.assertRaises(SystemExit) as raised,
        ):
            run_v2_1_online_candidate.main()

        self.assertIn("未发起真实调用", str(raised.exception))
        self.assertIn("停用", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
