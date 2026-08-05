from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.agent_orchestrator import _runtime_system_prompt
from src.combined_prompt_v7_real_runner import (
    QUESTION_ORDER,
    RESPONSE_CAP,
    execute_validation_v7,
)
from src.deepseek_internal_call_isolation_transport_mock_v2_3_4_2 import (
    CallIsolatedFrozenQuestionNativeToolMockClient,
    CallIsolatedLogicalClientV2_3_4_2,
    OfflineDeepSeekProviderV2_3_4_2,
)
from src.fact_schema import FactDimension
from src.mock_h2_registry import FrozenH2MockRegistry
from src.online_native_tool_candidate_combined_v7 import (
    COMBINED_PROMPT_VERSION,
    project_runtime_messages_combined_v7,
)
from src.prompt_contract import load_native_tool_agent_prompts_evidence_guard_v1
from src.report_validation import ReportFactReference
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


class CombinedPromptV7Tests(unittest.TestCase):
    def test_summary_selector_excludes_non_peak_months_and_prefers_ranked_fact(self) -> None:
        peak_dim = [FactDimension(name="month", value="2011-11")]
        prior_dim = [FactDimension(name="month", value="2011-10")]
        facts = [
            _fact("FACT-001", "peak_period", "2011-11", rank=1, dimensions=peak_dim),
            _fact("FACT-002", "sales_amount", "100", dimensions=prior_dim),
            _fact("FACT-003", "sales_amount", "200", dimensions=peak_dim),
            _fact("FACT-004", "sales_amount", "200", rank=1, dimensions=peak_dim),
            _fact("FACT-005", "incomplete_period", "2011-12"),
            _fact("FACT-006", "sales_amount", "300"),
            _fact(
                "FACT-007", "sales_amount", "300",
                dimensions=[FactDimension(name="segment", value="overall")],
            ),
        ]
        self.assertEqual(
            required_summary_fact_ids(facts),
            ["FACT-001", "FACT-004", "FACT-005", "FACT-006"],
        )

    def test_runtime_prompt_appends_exact_customer_argument_json(self) -> None:
        prompts = load_native_tool_agent_prompts_evidence_guard_v1()
        runtime = _runtime_system_prompt(
            prompts,
            session_id="SESSION-combined-v7-test",
            turn_id="TURN-001",
        )
        content = project_runtime_messages_combined_v7(
            [{"role": "system", "content": runtime}]
        )[0]["content"]
        self.assertIn(
            '{"period":"all_data","start_date":"__NONE__",'
            '"end_date":"__NONE__","include_coverage":true}',
            content,
        )

    def test_q04_q07_checkpoint_passes_offline(self) -> None:
        authority = validate_offline_request(confirmation=OFFLINE_CONFIRMATION)

        def transport_factory(_question_id: str):
            logical = CallIsolatedLogicalClientV2_3_4_2(
                CallIsolatedFrozenQuestionNativeToolMockClient()
            )
            return OfflineDeepSeekProviderV2_3_4_2(logical)

        with tempfile.TemporaryDirectory() as temp:
            result = execute_validation_v7(
                api_key="offline-combined-v7-key",
                registry=FrozenH2MockRegistry(),
                transport_factory=transport_factory,
                authority=authority,
                output_parent=Path(temp),
                run_id="combined_prompt_v7_q04_q07_offline_runner_test",
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
