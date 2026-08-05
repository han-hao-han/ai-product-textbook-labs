from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.agent_orchestrator import _runtime_system_prompt
from src.combined_prompt_v9_real_runner import (
    QUESTION_ORDER,
    RESPONSE_CAP,
    execute_validation_v9,
)
from src.deepseek_internal_call_isolation_transport_mock_v2_3_4_2 import (
    CallIsolatedFrozenQuestionNativeToolMockClient,
    CallIsolatedLogicalClientV2_3_4_2,
    OfflineDeepSeekProviderV2_3_4_2,
)
from src.fact_schema import FactDimension
from src.mock_h2_registry import FrozenH2MockRegistry
from src.online_native_tool_candidate_combined_v9 import (
    COMBINED_PROMPT_VERSION,
    project_runtime_messages_combined_v9,
)
from src.prompt_contract import load_native_tool_agent_prompts_evidence_guard_v1
from src.report_validation import ReportFactReference
from src.terminal_structural_guard_v9 import (
    TERMINAL_STRUCTURAL_PROMPT_PATH,
    required_summary_fact_ids_v9,
)
from src.terminal_summary_coverage_v7 import required_summary_fact_ids
from src.tool_routing_prompt_v1_real_runner import (
    OFFLINE_CONFIRMATION,
    validate_offline_request,
)


def _fact(
    fact_id: str, metric: str, value: str, *, rank=None, dimensions=None
) -> ReportFactReference:
    return ReportFactReference(
        fact_id=fact_id,
        metric=metric,
        value=value,
        display_value=value,
        unit="GBP" if metric == "sales_amount" else "calendar_month",
        rank=rank,
        dimensions=dimensions or [],
        period="complete_months_only",
        start_date=None,
        end_date=None,
    )


class CombinedPromptV9Tests(unittest.TestCase):
    def test_terminal_instruction_is_bounded_for_largest_summary_set(self) -> None:
        template = TERMINAL_STRUCTURAL_PROMPT_PATH.read_text(
            encoding="utf-8"
        ).strip()
        instruction = template.replace(
            "{{REQUIRED_FACT_IDS}}",
            ",".join(f"FACT-{index:03d}" for index in range(1, 18)),
        )
        self.assertLessEqual(len(instruction), 1200)
        self.assertIn("SLOT-004 and SLOT-005 have no evidence", instruction)
        self.assertIn("never combine different segments", instruction)

    def test_peak_summary_excludes_incomplete_period_only_in_v9(self) -> None:
        peak_dim = [FactDimension(name="month", value="2011-11")]
        facts = [
            _fact("FACT-001", "peak_period", "2011-11", rank=1, dimensions=peak_dim),
            _fact("FACT-002", "sales_amount", "200", rank=1, dimensions=peak_dim),
            _fact("FACT-003", "incomplete_period", "2011-12"),
        ]
        self.assertEqual(
            required_summary_fact_ids(facts),
            ["FACT-001", "FACT-002", "FACT-003"],
        )
        self.assertEqual(
            required_summary_fact_ids_v9(facts),
            ["FACT-001", "FACT-002"],
        )

    def test_runtime_prompt_appends_q10_control_message_guard(self) -> None:
        prompts = load_native_tool_agent_prompts_evidence_guard_v1()
        runtime = _runtime_system_prompt(
            prompts,
            session_id="SESSION-combined-v9-test",
            turn_id="TURN-001",
        )
        content = project_runtime_messages_combined_v9(
            [{"role": "system", "content": runtime}]
        )[0]["content"]
        self.assertIn("message", content)
        self.assertIn("supported_alternative", content)
        self.assertIn("forecasting_unsupported", content)
        self.assertIn("automatic_replenishment_unsupported", content)

    def test_q04_q05_q06_q10_checkpoint_passes_offline(self) -> None:
        authority = validate_offline_request(confirmation=OFFLINE_CONFIRMATION)

        def transport_factory(_question_id: str):
            logical = CallIsolatedLogicalClientV2_3_4_2(
                CallIsolatedFrozenQuestionNativeToolMockClient()
            )
            return OfflineDeepSeekProviderV2_3_4_2(logical)

        with tempfile.TemporaryDirectory() as temp:
            result = execute_validation_v9(
                api_key="offline-combined-v9-key",
                registry=FrozenH2MockRegistry(),
                transport_factory=transport_factory,
                authority=authority,
                output_parent=Path(temp),
                run_id="combined_prompt_v9_four_q_offline_runner_test",
            )
            self.assertTrue(result.passed, result.summary)
            self.assertEqual(
                result.summary["question_ids_executed"], list(QUESTION_ORDER)
            )
            self.assertEqual(result.summary["actual_response_attempts"], RESPONSE_CAP)
            self.assertEqual(
                result.summary["tool_selection_prompt_version"],
                COMBINED_PROMPT_VERSION,
            )


if __name__ == "__main__":
    unittest.main()
