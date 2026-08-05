from __future__ import annotations

import json
import tempfile
import unittest
from argparse import Namespace
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from scripts import run_q06_v2_2_flash_real_revalidation as runner
from src.mock_h2_registry import FrozenH2MockRegistry
from src.native_tool_transport_mock_v2_1_revision import (
    OfflineNativeToolTransportV2_1Revision,
)
from src.q06_provider_schema_revalidation_mock import (
    Q06ProviderSchemaRevalidationMockClient,
)
from src.q06_v2_2_flash_real_revalidation_plan import (
    Q06V2_2FlashRealPlanError,
    load_q06_v2_2_flash_real_plan,
    validate_q06_v2_2_flash_real_plan,
)


def exact_args() -> Namespace:
    return Namespace(
        question_id="Q06",
        approved_model_responses=3,
        automatic_retries=0,
        confirm_real_model_calls=runner.CONFIRMATION,
    )


def authorized_plan() -> dict:
    plan = deepcopy(load_q06_v2_2_flash_real_plan())
    plan["status"] = (
        "frozen_guarded_runner_offline_validated_and_real_call_"
        "authorized_pending_execution"
    )
    plan["authorization"].update(
        {
            "status": "authorized_by_user",
            "real_model_calls_allowed": True,
            "authorization_matches_frozen_plan": True,
        }
    )
    plan["implementation"]["guarded_runner_status"] = (
        "implemented_and_offline_validated"
    )
    return plan


class Q06V2_2FlashRealRevalidationTests(unittest.TestCase):
    def test_candidate_plan_has_no_real_call_authority(self) -> None:
        preflight = validate_q06_v2_2_flash_real_plan()
        self.assertEqual(preflight.model, "deepseek-v4-flash")
        self.assertEqual(preflight.response_attempt_upper_bound, 3)
        self.assertEqual(preflight.automatic_retry_count, 0)
        self.assertEqual(
            preflight.tool_choice_sequence,
            ("auto", "auto", "none"),
        )
        self.assertFalse(preflight.real_model_calls_allowed)
        plan = load_q06_v2_2_flash_real_plan()
        self.assertEqual(
            plan["status"],
            "frozen_real_validation_failed_pending_user_decision",
        )
        self.assertEqual(
            plan["implementation"]["guarded_runner_status"],
            "implemented_and_offline_validated",
        )
        self.assertTrue(
            plan["user_freeze"]["freeze_does_not_authorize_real_calls"]
        )

    def test_protocol_or_acceptance_drift_is_rejected(self) -> None:
        protocol = deepcopy(load_q06_v2_2_flash_real_plan())
        protocol["request_protocol"]["tool_choice_sequence"][-1] = "auto"
        with self.assertRaises(Q06V2_2FlashRealPlanError):
            validate_q06_v2_2_flash_real_plan(protocol)

        acceptance = deepcopy(load_q06_v2_2_flash_real_plan())
        acceptance["program_acceptance"]["chart_count"] = 1
        with self.assertRaises(Q06V2_2FlashRealPlanError):
            validate_q06_v2_2_flash_real_plan(acceptance)

    def test_consumed_authorization_cannot_run_again(self) -> None:
        argv = [
            "run_q06_v2_2_flash_real_revalidation.py",
            "--question-id",
            "Q06",
            "--approved-model-responses",
            "3",
            "--automatic-retries",
            "0",
            "--confirm-real-model-calls",
            runner.CONFIRMATION,
        ]
        with self.assertRaisesRegex(ValueError, "no separate real-call authority"):
            runner.validate_execution_request(exact_args())

    def test_only_exact_future_authorized_request_can_create_authority(self) -> None:
        authority = runner.validate_execution_request(
            exact_args(), plan=authorized_plan()
        )
        self.assertEqual(authority.question_id, "Q06")
        self.assertEqual(authority.model, "deepseek-v4-flash")
        wrong = exact_args()
        wrong.approved_model_responses = 4
        with self.assertRaises(ValueError):
            runner.validate_execution_request(wrong, plan=authorized_plan())

    def test_offline_runner_saves_three_response_success_evidence(self) -> None:
        transport = OfflineNativeToolTransportV2_1Revision(
            Q06ProviderSchemaRevalidationMockClient(),
            expected_model="deepseek-v4-flash",
        )
        with tempfile.TemporaryDirectory(
            dir=runner.PROJECT_ROOT / "results" / "raw"
        ) as temporary:
            result = runner.execute_v2_2_validation(
                api_key="offline-v22-key",
                registry=FrozenH2MockRegistry(),
                transport=transport,
                output_parent=Path(temporary),
                run_id="offline-v22-success",
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
            self.assertEqual(result.summary["failed_transport_attempts"], 0)
            self.assertEqual(
                [request.tool_choice for request in transport.requests],
                ["auto", "auto", "none"],
            )
            self.assertEqual(result.case_payload["outcome"]["status"], "completed")
            self.assertEqual(len(result.case_payload["outcome"]["charts"]), 2)
            self.assertEqual(
                result.case_payload["outcome"]["report_validation"]["status"],
                "passed",
            )
            self.assertTrue((result.output_dir / "Q06.json").exists())
            self.assertTrue((result.output_dir / "summary.json").exists())
            evidence = json.loads(
                (result.output_dir / "Q06.json").read_text(encoding="utf-8")
            )
            self.assertNotIn("offline-v22-key", json.dumps(evidence))


if __name__ == "__main__":
    unittest.main()
