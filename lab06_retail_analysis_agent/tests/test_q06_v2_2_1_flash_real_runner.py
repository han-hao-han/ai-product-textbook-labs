from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import run_q06_v2_2_1_flash_real_revalidation as runner
from scripts.validate_q06_v2_2_1_flash_real_runner import (
    InvalidFirstResponseClient,
    LengthTerminalResponseClient,
    authorized_plan_copy,
    exact_args,
)
from src.mock_h2_registry import FrozenH2MockRegistry
from src.native_tool_transport_mock_v2_1_revision import (
    OfflineNativeToolTransportV2_1Revision,
)
from src.q06_provider_schema_revalidation_mock import (
    Q06ProviderSchemaRevalidationMockClient,
)


class Q06V2_2_1FlashRealRunnerTests(unittest.TestCase):
    def test_current_gate_stops_before_api_key_read(self) -> None:
        with patch.object(runner, "parse_args", return_value=exact_args()), patch.object(
            runner.core,
            "_load_api_key",
            side_effect=AssertionError("API key must not be read"),
        ):
            with self.assertRaisesRegex(SystemExit, "authorization gate"):
                runner.main()

    def test_only_exact_authorized_request_creates_authority(self) -> None:
        authority = runner.validate_execution_request(
            exact_args(),
            plan=authorized_plan_copy(),
        )
        self.assertEqual(authority.question_id, "Q06")
        self.assertEqual(authority.model, "deepseek-v4-flash")
        wrong = exact_args()
        wrong.approved_model_responses = 4
        with self.assertRaises(ValueError):
            runner.validate_execution_request(
                wrong,
                plan=authorized_plan_copy(),
            )

    def _execute(self, logical_client, *, run_id: str):
        transport = OfflineNativeToolTransportV2_1Revision(
            logical_client,
            expected_model="deepseek-v4-flash",
        )
        temporary = tempfile.TemporaryDirectory(
            dir=runner.PROJECT_ROOT / "results" / "raw"
        )
        self.addCleanup(temporary.cleanup)
        result = runner.execute_v2_2_1_validation(
            api_key=f"offline-{run_id}-key",
            registry=FrozenH2MockRegistry(),
            transport=transport,
            output_parent=Path(temporary.name),
            run_id=run_id,
        )
        return result, transport

    def test_success_uses_terminal_json_and_saves_safe_evidence(self) -> None:
        result, transport = self._execute(
            Q06ProviderSchemaRevalidationMockClient(),
            run_id="v221-success",
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
        self.assertEqual(
            [request.tool_choice for request in transport.requests],
            ["auto", "auto", "none"],
        )
        self.assertEqual(
            [request.response_format for request in transport.requests],
            runner.REQUIRED_RESPONSE_FORMATS,
        )
        evidence = "\n".join(
            path.read_text(encoding="utf-8")
            for path in result.output_dir.glob("*.json")
        )
        self.assertNotIn("offline-v221-success-key", evidence)
        case = json.loads(
            (result.output_dir / "Q06.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            [
                step["requested_response_format"]
                for step in case["native_model_trace"]
            ],
            runner.REQUIRED_RESPONSE_FORMATS,
        )

    def test_first_failure_stops_after_one_response(self) -> None:
        result, transport = self._execute(
            InvalidFirstResponseClient(),
            run_id="v221-first-failure",
        )
        self.assertFalse(result.passed)
        self.assertEqual(result.summary["actual_model_response_attempts"], 1)
        self.assertEqual(len(transport.requests), 1)
        self.assertEqual(len(result.case_payload["outcome"]["tool_calls"]), 0)

    def test_finish_reason_length_is_program_failure(self) -> None:
        result, transport = self._execute(
            LengthTerminalResponseClient(),
            run_id="v221-length-failure",
        )
        self.assertFalse(result.passed)
        self.assertEqual(result.summary["actual_model_response_attempts"], 3)
        self.assertEqual(len(transport.requests), 3)
        self.assertIn(
            "provider_finish_reason_length",
            result.case_payload["program_failures"],
        )


if __name__ == "__main__":
    unittest.main()
