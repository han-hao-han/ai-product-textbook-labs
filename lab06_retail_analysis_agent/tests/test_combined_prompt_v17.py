from __future__ import annotations

import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace

from src.terminal_narrative_fact_expression_v17 import (
    terminal_narrative_fact_issues_v17,
)
from src.combined_prompt_v17_q04_q05_real_runner import (
    execute_validation_v17_q04_q05,
)
from src.deepseek_internal_call_isolation_transport_mock_v2_3_4_2 import (
    CallIsolatedFrozenQuestionNativeToolMockClient,
    CallIsolatedLogicalClientV2_3_4_2,
    OfflineDeepSeekProviderV2_3_4_2,
)
from src.mock_h2_registry import FrozenH2MockRegistry
from src.tool_routing_prompt_v1_real_runner import (
    OFFLINE_CONFIRMATION,
    validate_offline_request,
)


def _fact(value: str, display: str, fact_id: str = "FACT-001") -> SimpleNamespace:
    return SimpleNamespace(
        evidence_type="FACT", value=value, display_value=display,
        fact_id=fact_id, metric="sales_amount", rank=None,
        start_date=None, end_date=None, dimensions=[],
    )


class CombinedPromptV17Tests(unittest.TestCase):
    def test_chart_section_may_carry_unexpressed_plot_rows(self) -> None:
        sections = [SimpleNamespace(claims=[]) for _ in range(6)]
        sections[2] = SimpleNamespace(claims=[SimpleNamespace(
            statement="图表展示完整序列。", evidence=[_fact("1503866.78", "£1,503,866.78")]
        )])
        response = SimpleNamespace(report=SimpleNamespace(sections=sections))
        self.assertEqual(terminal_narrative_fact_issues_v17(response), [])

    def test_narrative_section_still_requires_fact_value(self) -> None:
        sections = [SimpleNamespace(claims=[]) for _ in range(6)]
        sections[1] = SimpleNamespace(claims=[SimpleNamespace(
            statement="关键指标见证据。", evidence=[_fact("5152002", "5,152,002", "FACT-009")]
        )])
        response = SimpleNamespace(report=SimpleNamespace(sections=sections))
        issues = terminal_narrative_fact_issues_v17(response)
        self.assertEqual([item["code"] for item in issues], ["fact_value_not_expressed"])

    def test_q04_q05_checkpoint_passes_offline(self) -> None:
        authority = validate_offline_request(confirmation=OFFLINE_CONFIRMATION)

        def transport_factory(_question_id: str):
            logical = CallIsolatedLogicalClientV2_3_4_2(
                CallIsolatedFrozenQuestionNativeToolMockClient()
            )
            return OfflineDeepSeekProviderV2_3_4_2(logical)

        with tempfile.TemporaryDirectory() as temp:
            result = execute_validation_v17_q04_q05(
                api_key="offline-combined-v17-key",
                registry=FrozenH2MockRegistry(),
                transport_factory=transport_factory,
                authority=authority,
                output_parent=Path(temp),
                run_id="combined_prompt_v17_q04_q05_offline_runner_test",
            )
            self.assertTrue(result.passed, result.summary)
            self.assertEqual(result.summary["question_ids_executed"], ["Q04", "Q05"])


if __name__ == "__main__":
    unittest.main()
