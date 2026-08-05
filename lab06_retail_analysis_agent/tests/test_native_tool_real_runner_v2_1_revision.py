from __future__ import annotations

import unittest
from argparse import Namespace
from unittest.mock import patch

from scripts import run_native_tool_real_validation_v2_1_revision as runner
from src.online_native_tool_candidate_v2_1_revision import (
    NATIVE_REAL_MODEL_CONFIRMATION,
)


def valid_args() -> Namespace:
    return Namespace(
        question_id=["Q06", "Q08", "Q09"],
        approved_model_responses=5,
        automatic_retries=0,
        confirm_real_model_calls=NATIVE_REAL_MODEL_CONFIRMATION,
    )


class NativeToolRealRunnerV2_1RevisionTests(unittest.TestCase):
    def test_consumed_authorization_blocks_second_execution(self) -> None:
        with self.assertRaises(ValueError) as raised:
            runner.validate_execution_request(valid_args())
        self.assertIn("no compatible real-call authority", str(raised.exception))

    def test_ten_response_cap_is_rejected_before_key_read(self) -> None:
        args = valid_args()
        args.approved_model_responses = 10
        argv = [
            "run_native_tool_real_validation_v2_1_revision.py",
            "--question-id",
            "Q06",
            "--question-id",
            "Q08",
            "--question-id",
            "Q09",
            "--approved-model-responses",
            "10",
            "--automatic-retries",
            "0",
            "--confirm-real-model-calls",
            NATIVE_REAL_MODEL_CONFIRMATION,
        ]
        with (
            patch("sys.argv", argv),
            patch.object(
                runner,
                "_load_api_key",
                side_effect=AssertionError("key must not be read"),
            ),
            self.assertRaises(SystemExit) as raised,
        ):
            runner.main()
        self.assertIn("exactly five", str(raised.exception))

    def test_wrong_question_order_is_rejected_before_key_read(self) -> None:
        args = valid_args()
        args.question_id = ["Q08", "Q06", "Q09"]
        with self.assertRaises(ValueError):
            runner.validate_execution_request(args)

    def test_retry_or_confirmation_drift_is_rejected(self) -> None:
        retry = valid_args()
        retry.automatic_retries = 1
        with self.assertRaises(ValueError):
            runner.validate_execution_request(retry)

        confirmation = valid_args()
        confirmation.confirm_real_model_calls = ""
        with self.assertRaises(ValueError):
            runner.validate_execution_request(confirmation)

    def test_consumed_authority_stops_before_key_or_online_candidate(self) -> None:
        argv = [
            "run_native_tool_real_validation_v2_1_revision.py",
            "--question-id",
            "Q06",
            "--question-id",
            "Q08",
            "--question-id",
            "Q09",
            "--approved-model-responses",
            "5",
            "--automatic-retries",
            "0",
            "--confirm-real-model-calls",
            NATIVE_REAL_MODEL_CONFIRMATION,
        ]
        with (
            patch("sys.argv", argv),
            patch.object(
                runner,
                "_load_api_key",
                side_effect=AssertionError("key must not be read again"),
            ),
            patch.object(
                runner,
                "NativeToolOnlineCandidateV2_1Revision",
                side_effect=AssertionError("online candidate must not be created"),
            ),
            self.assertRaises(SystemExit) as raised,
        ):
            runner.main()
        self.assertIn("no compatible real-call authority", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
