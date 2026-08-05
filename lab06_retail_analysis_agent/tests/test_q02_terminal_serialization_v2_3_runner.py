from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.deepseek_report_terminal_transport_mock_v2_3 import (
    FrozenNativeLogicalClientV2_3,
    OfflineDeepSeekProviderV2_3,
)
from src.mock_h2_registry import FrozenH2MockRegistry
from src.q01_q10_batch_a_offline_mock import (
    BatchAEvidenceCompleteMockClient,
)
from src.q02_terminal_serialization_v2_3_runner import (
    OFFLINE_CONFIRMATION,
    REAL_CONFIRMATION,
    Q02ExecutionAuthorityV2_3,
    Q02TerminalV2_3RunnerError,
    consume_real_authority,
    execute_q02_validation,
    validate_offline_execution_request,
    validate_real_execution_request,
)


class Q02TerminalSerializationV2_3RunnerTests(unittest.TestCase):
    def test_offline_success_path_uses_two_endpoints_and_new_harness(self) -> None:
        provider = OfflineDeepSeekProviderV2_3(
            FrozenNativeLogicalClientV2_3(
                BatchAEvidenceCompleteMockClient()
            )
        )
        authority = validate_offline_execution_request(
            confirmation=OFFLINE_CONFIRMATION
        )
        with tempfile.TemporaryDirectory() as temporary:
            result = execute_q02_validation(
                api_key="offline-q02-v2-3-secret",
                registry=FrozenH2MockRegistry(),
                transport=provider,
                authority=authority,
                output_parent=Path(temporary),
                run_id="offline-success",
            )
            evidence = (result.output_dir / "Q02.json").read_text(
                encoding="utf-8"
            )
        self.assertTrue(result.passed, result.summary)
        self.assertEqual(
            result.summary["status"],
            "passed_deterministic_pending_manual_review",
        )
        self.assertEqual(result.summary["actual_response_attempts"], 2)
        self.assertFalse(result.summary["authorization_consumed"])
        self.assertNotIn("offline-q02-v2-3-secret", evidence)

    def test_real_authority_is_consumed_once_before_transport(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            authority = Q02ExecutionAuthorityV2_3(
                mode="real_transport",
                authorization_id="unit-test-single-use-authority",
            )
            marker = consume_real_authority(
                authority,
                consumption_root=root,
            )
            self.assertTrue(marker.exists())
            with self.assertRaisesRegex(
                Q02TerminalV2_3RunnerError,
                "already been consumed",
            ):
                consume_real_authority(
                    authority,
                    consumption_root=root,
                )

    def test_consumed_project_authority_is_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(
                Q02TerminalV2_3RunnerError,
                "no exact unconsumed authority",
            ):
                validate_real_execution_request(
                    question_id="Q02",
                    model="deepseek-v4-flash",
                    approved_model_responses=2,
                    automatic_retries=0,
                    confirmation=REAL_CONFIRMATION,
                    consumption_root=Path(temporary),
                )

    def test_wrong_scope_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(Q02TerminalV2_3RunnerError):
                validate_real_execution_request(
                    question_id="Q06",
                    model="deepseek-v4-flash",
                    approved_model_responses=2,
                    automatic_retries=0,
                    confirmation=REAL_CONFIRMATION,
                    consumption_root=Path(temporary),
                )


if __name__ == "__main__":
    unittest.main()
