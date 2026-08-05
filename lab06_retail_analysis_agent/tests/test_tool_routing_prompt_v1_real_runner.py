from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import json
from types import SimpleNamespace

from src.deepseek_internal_call_isolation_transport_mock_v2_3_4_2 import (
    CallIsolatedFrozenQuestionNativeToolMockClient,
    CallIsolatedLogicalClientV2_3_4_2,
    OfflineDeepSeekProviderV2_3_4_2,
)
from src.mock_h2_registry import FrozenH2MockRegistry
from src.tool_routing_prompt_v1_real_runner import (
    OFFLINE_CONFIRMATION,
    ToolRoutingRealRunnerError,
    _root_failure,
    execute_validation,
    validate_offline_request,
    validate_real_request,
)


class ToolRoutingPromptV1RealRunnerTests(unittest.TestCase):
    def test_report_failure_metadata_accepts_pydantic_style_evidence(self) -> None:
        class DumpableEvidence:
            def model_dump(self, *, mode: str):
                self.assert_mode = mode
                return {
                    "report_validation": {
                        "issues": [{"code": "unsupported_quantity_superlative"}]
                    }
                }

        outcome = SimpleNamespace(
            error_stage="report_validation",
            error_message="report failed",
            rejected_report_evidence=DumpableEvidence(),
        )
        self.assertEqual(
            _root_failure(outcome, ["unexpected_terminal_status"]),
            ("report_validation", ["unsupported_quantity_superlative"]),
        )

    def test_report_failure_metadata_accepts_dataclass_style_evidence(self) -> None:
        outcome = SimpleNamespace(
            error_stage="report_validation",
            error_message="report failed",
            rejected_report_evidence=SimpleNamespace(
                report_validation=SimpleNamespace(
                    issues=(SimpleNamespace(code="unsupported_quantity_superlative"),)
                )
            ),
        )
        self.assertEqual(
            _root_failure(outcome, ["unexpected_terminal_status"]),
            ("report_validation", ["unsupported_quantity_superlative"]),
        )

    def test_real_gate_requires_exact_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(
                ToolRoutingRealRunnerError, "exact real confirmation"
            ):
                validate_real_request(
                    model="deepseek-v4-flash",
                    response_cap=27,
                    automatic_retries=0,
                    confirmation="wrong",
                    consumption_root=Path(temp),
                )

    def test_q02_first_offline_batch_saves_all_cases(self) -> None:
        authority = validate_offline_request(
            confirmation=OFFLINE_CONFIRMATION
        )

        def transport_factory(_question_id: str):
            logical = CallIsolatedLogicalClientV2_3_4_2(
                CallIsolatedFrozenQuestionNativeToolMockClient()
            )
            return OfflineDeepSeekProviderV2_3_4_2(logical)

        with tempfile.TemporaryDirectory() as temp:
            result = execute_validation(
                api_key="offline-tool-routing-runner-key",
                registry=FrozenH2MockRegistry(),
                transport_factory=transport_factory,
                authority=authority,
                output_parent=Path(temp),
                run_id="tool_routing_prompt_v1_offline_runner_test",
            )
            self.assertTrue(result.passed, result.summary)
            self.assertEqual(result.summary["question_ids_executed"][0], "Q02")
            self.assertEqual(len(result.summary["question_ids_executed"]), 10)
            self.assertEqual(result.summary["actual_response_attempts"], 27)
            self.assertEqual(
                result.summary["model_visible_internal_call_values"], 0
            )
            self.assertTrue((result.output_dir / "Q02.json").exists())
            self.assertTrue((result.output_dir / "Q10.json").exists())
            self.assertTrue((result.output_dir / "summary.json").exists())
            self.assertTrue((result.output_dir / "run_state.json").exists())
            state = json.loads(
                (result.output_dir / "run_state.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(state["attempted"], 27)
            self.assertEqual(len(set(state["http_response_files"])), 27)
            self.assertEqual(len(set(state["parsed_response_files"])), 27)



if __name__ == "__main__":
    unittest.main()
