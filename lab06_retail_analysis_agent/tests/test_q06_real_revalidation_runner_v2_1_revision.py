from __future__ import annotations

import json
import tempfile
import unittest
from argparse import Namespace
from copy import deepcopy
from pathlib import Path
from typing import Any
from unittest.mock import patch

from scripts import run_q06_real_revalidation_v2_1_revision as runner
from src.deepseek_client import ChatCompletionResult, ProviderToolCall
from src.deepseek_provider_schema_adapter_v2_1_revision import (
    DEEPSEEK_NONE_SENTINEL,
)
from src.mock_h2_registry import FrozenH2MockRegistry
from src.native_tool_transport_mock_v2_1_revision import (
    OfflineNativeToolTransportV2_1Revision,
)
from src.q06_provider_schema_revalidation_mock import (
    Q06ProviderSchemaRevalidationMockClient,
)
from src.q06_real_revalidation_plan_v2_1_revision import (
    load_q06_real_revalidation_plan,
)


def valid_args() -> Namespace:
    return Namespace(
        question_id="Q06",
        approved_model_responses=3,
        automatic_retries=0,
        confirm_real_model_calls=runner.Q06_REAL_REVALIDATION_CONFIRMATION,
    )


def authorized_plan() -> dict[str, Any]:
    plan = deepcopy(load_q06_real_revalidation_plan())
    plan["status"] = (
        "frozen_guarded_runner_offline_validated_and_real_call_"
        "authorized_pending_execution"
    )
    plan["compatible_authorization"] = {
        "status": "authorized_by_user",
        "question_ids": ["Q06"],
        "model": "deepseek-v4-pro",
        "response_attempt_upper_bound": 3,
        "automatic_retry_count": 0,
        "authorization_matches_frozen_plan": True,
    }
    return plan


def unauthorized_plan() -> dict[str, Any]:
    plan = deepcopy(load_q06_real_revalidation_plan())
    plan["status"] = (
        "frozen_guarded_runner_offline_validated_pending_separate_authorization"
    )
    plan.pop("compatible_authorization", None)
    return plan


class InvalidFirstQ06ResponseClient:
    def complete_strict_tools(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: str = "auto",
    ) -> ChatCompletionResult:
        return ChatCompletionResult(
            finish_reason="tool_calls",
            content=None,
            tool_calls=(
                ProviderToolCall(
                    provider_call_id="invalid-first",
                    tool_name="analyze_time_trend",
                    arguments={
                        "period": "complete_months_only",
                        "start_date": DEEPSEEK_NONE_SENTINEL,
                        "end_date": DEEPSEEK_NONE_SENTINEL,
                        "grain": "monthly",
                        "metric": "sales_amount",
                        "exclude_incomplete_periods": True,
                    },
                ),
            ),
            raw_response={"offline_invalid_first": True},
            usage=None,
        )


class Q06RealRevalidationRunnerV2_1RevisionTests(unittest.TestCase):
    def test_consumed_real_authority_blocks_another_execution(self) -> None:
        with self.assertRaises(ValueError) as raised:
            runner.validate_execution_request(valid_args())
        self.assertIn("no separate real-call authority", str(raised.exception))

    def test_exact_authorized_copy_passes_execution_gate(self) -> None:
        result = runner.validate_execution_request(
            valid_args(), plan=authorized_plan()
        )
        self.assertEqual(
            result.plan["compatible_authorization"]["question_ids"], ["Q06"]
        )
        self.assertEqual(result.response_attempt_upper_bound, 3)

    def test_scope_cap_retry_and_confirmation_drift_are_rejected(self) -> None:
        plan = authorized_plan()
        wrong_question = valid_args()
        wrong_question.question_id = "Q08"
        with self.assertRaises(ValueError):
            runner.validate_execution_request(wrong_question, plan=plan)

        wrong_cap = valid_args()
        wrong_cap.approved_model_responses = 4
        with self.assertRaises(ValueError):
            runner.validate_execution_request(wrong_cap, plan=plan)

        retry = valid_args()
        retry.automatic_retries = 1
        with self.assertRaises(ValueError):
            runner.validate_execution_request(retry, plan=plan)

        confirmation = valid_args()
        confirmation.confirm_real_model_calls = ""
        with self.assertRaises(ValueError):
            runner.validate_execution_request(confirmation, plan=plan)

    def test_main_blocks_before_api_key_read(self) -> None:
        argv = [
            "run_q06_real_revalidation_v2_1_revision.py",
            "--question-id",
            "Q06",
            "--approved-model-responses",
            "3",
            "--automatic-retries",
            "0",
            "--confirm-real-model-calls",
            runner.Q06_REAL_REVALIDATION_CONFIRMATION,
        ]
        with (
            patch("sys.argv", argv),
            patch.object(
                runner,
                "_load_api_key",
                side_effect=AssertionError("key must not be read"),
            ),
            patch.object(
                runner,
                "load_q06_real_revalidation_plan",
                return_value=unauthorized_plan(),
            ),
            self.assertRaises(SystemExit) as raised,
        ):
            runner.main()
        self.assertIn("no separate real-call authority", str(raised.exception))

    def test_core_rejects_real_transport_without_validated_authority(self) -> None:
        with (
            patch.object(
                runner,
                "NativeToolOnlineCandidateV2_1Revision",
                side_effect=AssertionError("online client must not be created"),
            ),
            self.assertRaises(ValueError) as raised,
        ):
            runner.execute_q06_validation(
                api_key="not-used",
                registry=FrozenH2MockRegistry(),
                transport=None,
                output_parent=runner.PROJECT_ROOT / "results" / "raw",
                run_id="must-not-run",
            )
        self.assertIn("validated execution authority", str(raised.exception))

    def test_success_uses_exact_three_responses_and_saves_evidence(self) -> None:
        transport = OfflineNativeToolTransportV2_1Revision(
            Q06ProviderSchemaRevalidationMockClient(),
            expected_model="deepseek-v4-pro",
        )
        with tempfile.TemporaryDirectory(
            dir=runner.PROJECT_ROOT / "results" / "raw"
        ) as temporary:
            result = runner.execute_q06_validation(
                api_key="offline-success-key",
                registry=FrozenH2MockRegistry(),
                transport=transport,
                output_parent=Path(temporary),
                run_id="offline-success",
            )
            self.assertFalse(result.passed)
            self.assertIn(
                "fixed_question_validation_failed",
                result.case_payload["program_failures"],
            )
            self.assertEqual(
                result.case_payload["fixed_question_validation"]["status"],
                "protocol_and_dataflow_passed",
            )
            self.assertEqual(result.summary["actual_model_response_attempts"], 3)
            self.assertEqual(len(transport.requests), 3)
            self.assertTrue((result.output_dir / "Q06.json").exists())
            self.assertTrue((result.output_dir / "summary.json").exists())
            case = json.loads(
                (result.output_dir / "Q06.json").read_text(encoding="utf-8")
            )
            self.assertEqual(len(case["outcome"]["raw_responses"]), 3)
            self.assertEqual(case["usage"]["responses_with_usage"], 3)
            self.assertEqual(case["usage"]["total_tokens"], 360)
            self.assertEqual(
                case["native_model_trace"][0]["selected_arguments"]["start_date"],
                DEEPSEEK_NONE_SENTINEL,
            )
            self.assertIsNone(
                case["native_model_trace"][0]["normalized_arguments"]["start_date"]
            )
            saved = json.dumps(case, ensure_ascii=False)
            self.assertNotIn("offline-success-key", saved)
            self.assertNotIn("Bearer ", saved)

    def test_first_failure_stops_after_one_and_saves_raw_failure_evidence(self) -> None:
        transport = OfflineNativeToolTransportV2_1Revision(
            InvalidFirstQ06ResponseClient(),
            expected_model="deepseek-v4-pro",
        )
        with tempfile.TemporaryDirectory(
            dir=runner.PROJECT_ROOT / "results" / "raw"
        ) as temporary:
            result = runner.execute_q06_validation(
                api_key="offline-failure-key",
                registry=FrozenH2MockRegistry(),
                transport=transport,
                output_parent=Path(temporary),
                run_id="offline-failure",
            )
            self.assertFalse(result.passed)
            self.assertEqual(result.summary["actual_model_response_attempts"], 1)
            self.assertEqual(len(transport.requests), 1)
            case = json.loads(
                (result.output_dir / "Q06.json").read_text(encoding="utf-8")
            )
            self.assertEqual(len(case["outcome"]["raw_responses"]), 1)
            self.assertEqual(case["usage"]["responses_with_usage"], 1)
            self.assertEqual(case["outcome"]["error_stage"], "model_response")
            self.assertEqual(
                case["native_model_trace"][0]["selected_arguments"]["grain"],
                "monthly",
            )
            self.assertEqual(case["outcome"]["tool_calls"], [])

    def test_evidence_writer_rejects_secret_and_authorization_material(self) -> None:
        with self.assertRaises(ValueError):
            runner._safe_json_text(
                {"value": "sensitive-key"}, api_key="sensitive-key"
            )
        with self.assertRaises(ValueError):
            runner._safe_json_text(
                {"Authorization": "Bearer hidden"}, api_key="different"
            )


if __name__ == "__main__":
    unittest.main()
