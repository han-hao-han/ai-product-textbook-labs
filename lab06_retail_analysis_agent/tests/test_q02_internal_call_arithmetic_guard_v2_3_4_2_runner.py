from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.deepseek_internal_call_isolation_transport_mock_v2_3_4_2 import (
    CallIsolatedFrozenQuestionNativeToolMockClient,
    CallIsolatedLogicalClientV2_3_4_2,
    OfflineDeepSeekProviderV2_3_4_2,
)
from src.mock_h2_registry import FrozenH2MockRegistry
from src.q02_internal_call_arithmetic_guard_v2_3_4_2_runner import (
    OFFLINE_CONFIRMATION,
    Q02ProtocolGuardRunnerError,
    _root_failure,
    execute_q02,
    validate_offline_execution_request,
    validate_real_execution_request,
)


class Q02ProtocolGuardV2_3_4_2RunnerTests(unittest.TestCase):
    def test_tool_plan_error_precedes_harness_cascade(self) -> None:
        outcome = SimpleNamespace(
            error_stage="model_response",
            error_message="Q02 model selected an unsupported tool sequence",
        )
        stage, codes = _root_failure(
            outcome=outcome,
            failures=[
                "unexpected_terminal_status",
                "new_harness_deterministic_acceptance_failed",
                "unexpected_tool_sequence",
            ],
        )
        self.assertEqual(stage, "model_response")
        self.assertEqual(
            codes, ["model_selected_unsupported_tool_sequence"]
        )

    def test_offline_gate_requires_exact_confirmation(self) -> None:
        with self.assertRaisesRegex(
            Q02ProtocolGuardRunnerError, "offline confirmation"
        ):
            validate_offline_execution_request(confirmation="wrong")

    def test_real_gate_requires_exact_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(
                Q02ProtocolGuardRunnerError, "exact real confirmation"
            ):
                validate_real_execution_request(
                    question_id="Q02",
                    model="deepseek-v4-flash",
                    approved_model_responses=3,
                    automatic_retries=0,
                    confirmation="wrong",
                    consumption_root=Path(temp),
                )

    def test_offline_runner_saves_crash_safe_evidence(self) -> None:
        authority = validate_offline_execution_request(
            confirmation=OFFLINE_CONFIRMATION
        )
        logical = CallIsolatedLogicalClientV2_3_4_2(
            CallIsolatedFrozenQuestionNativeToolMockClient()
        )
        provider = OfflineDeepSeekProviderV2_3_4_2(logical)
        with tempfile.TemporaryDirectory() as temp:
            result = execute_q02(
                api_key="offline-runner-key-not-real",
                registry=FrozenH2MockRegistry(),
                transport=provider,
                authority=authority,
                output_parent=Path(temp),
                run_id="q02_v2_3_4_2_offline_gate_test",
            )
            self.assertTrue(result.passed, result.summary)
            self.assertEqual(
                result.summary["status"],
                "passed_deterministic_pending_manual_review",
            )
            self.assertEqual(result.summary["actual_response_attempts"], 3)
            self.assertEqual(result.summary["completed_model_responses"], 3)
            self.assertEqual(
                result.summary["failed_transport_or_provider_attempts"], 0
            )
            self.assertEqual(
                result.summary["model_visible_internal_call_values"], 0
            )
            self.assertTrue(
                result.summary["raw_parsed_mapped_saved_separately"]
            )
            self.assertTrue((result.output_dir / "Q02.json").exists())
            self.assertTrue((result.output_dir / "summary.json").exists())
            self.assertTrue((result.output_dir / "run_state.json").exists())


if __name__ == "__main__":
    unittest.main()
