from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.combined_prompt_v18_real_runner import (
    execute_validation_v18_full, execute_validation_v18_q04,
)
from src.deepseek_internal_call_isolation_transport_mock_v2_3_4_2 import (
    CallIsolatedFrozenQuestionNativeToolMockClient,
    CallIsolatedLogicalClientV2_3_4_2, OfflineDeepSeekProviderV2_3_4_2,
)
from src.mock_h2_registry import FrozenH2MockRegistry
from src.terminal_narrative_evidence_expression_v18 import terminal_narrative_evidence_issues_v18
from src.tool_routing_prompt_v1_real_runner import OFFLINE_CONFIRMATION, validate_offline_request


class CombinedPromptV18Tests(unittest.TestCase):
    def test_chart_section_does_not_require_request_literal(self) -> None:
        sections = [SimpleNamespace(claims=[]) for _ in range(6)]
        request = SimpleNamespace(
            evidence_type="REQUEST", value="2011-12", request_id="REQUEST-002",
            parameter_name="excluded_period",
        )
        sections[2] = SimpleNamespace(claims=[SimpleNamespace(
            statement="图表使用完整月份口径。", evidence=[request]
        )])
        response = SimpleNamespace(report=SimpleNamespace(sections=sections))
        self.assertEqual(terminal_narrative_evidence_issues_v18(response), [])

    def test_q04_and_full_offline_runners_pass(self) -> None:
        authority = validate_offline_request(confirmation=OFFLINE_CONFIRMATION)
        def factory(_question_id: str):
            logical = CallIsolatedLogicalClientV2_3_4_2(CallIsolatedFrozenQuestionNativeToolMockClient())
            return OfflineDeepSeekProviderV2_3_4_2(logical)
        with tempfile.TemporaryDirectory() as temp:
            q04 = execute_validation_v18_q04(
                api_key="offline-v18-q04", registry=FrozenH2MockRegistry(),
                transport_factory=factory, authority=authority,
                output_parent=Path(temp), run_id="v18_q04_offline",
            )
            full = execute_validation_v18_full(
                api_key="offline-v18-full", registry=FrozenH2MockRegistry(),
                transport_factory=factory, authority=authority,
                output_parent=Path(temp), run_id="v18_full_offline",
            )
        self.assertTrue(q04.passed, q04.summary)
        self.assertTrue(full.passed, full.summary)


if __name__ == "__main__":
    unittest.main()
