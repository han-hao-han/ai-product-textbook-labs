from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.combined_prompt_v13_real_runner import (
    QUESTION_ORDER,
    RESPONSE_CAP,
    execute_validation_v13,
)
from src.deepseek_internal_call_isolation_transport_mock_v2_3_4_2 import (
    CallIsolatedFrozenQuestionNativeToolMockClient,
    CallIsolatedLogicalClientV2_3_4_2,
    OfflineDeepSeekProviderV2_3_4_2,
)
from src.mock_h2_registry import FrozenH2MockRegistry
from src.online_native_tool_candidate_combined_v13 import COMBINED_PROMPT_VERSION
from src.report_validation import ReportFactReference, ReportClaim, ReportSection
from src.terminal_report_feedback_v13 import terminal_report_issues_v13
from src.tool_routing_prompt_v1_real_runner import (
    EXPECTED_RESPONSES,
    OFFLINE_CONFIRMATION,
    validate_offline_request,
)


def _response(statement: str):
    evidence = ReportFactReference(
        fact_id="FACT-001", metric="peak_period", value="2011-11",
        display_value="2011-11", unit="calendar_month", rank=1,
        dimensions=[], period="complete_months_only",
        start_date=None, end_date=None,
    )
    sections = [
        ReportSection(name=name, claims=[ReportClaim(statement="说明", evidence=[])])
        for name in (
            "用户问题与分析口径", "关键经营发现", "工具证据与图表",
            "有限解释", "经营建议", "数据与分析限制",
        )
    ]
    sections[1] = ReportSection(
        name="关键经营发现",
        claims=[ReportClaim(statement=statement, evidence=[evidence])],
    )
    return SimpleNamespace(report=SimpleNamespace(sections=sections))


class CombinedPromptV13Tests(unittest.TestCase):
    def test_validator_returns_exact_non_local_literal_and_location(self) -> None:
        issues = terminal_report_issues_v13(
            _response("排除2011-12后，峰值月份为2011-11。")
        )
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["code"], "untraceable_numeric_token")
        self.assertEqual(issues[0]["location"], "sections[1].claims[0]")
        self.assertEqual(issues[0]["unsupported_literal"], "2011-12")
        self.assertEqual(
            terminal_report_issues_v13(_response("峰值月份为2011-11。")), []
        )

    def test_q04_runner_accepts_baseline_without_forcing_correction(self) -> None:
        authority = validate_offline_request(confirmation=OFFLINE_CONFIRMATION)

        def transport_factory(_question_id: str):
            logical = CallIsolatedLogicalClientV2_3_4_2(
                CallIsolatedFrozenQuestionNativeToolMockClient()
            )
            return OfflineDeepSeekProviderV2_3_4_2(logical)

        with tempfile.TemporaryDirectory() as temp:
            result = execute_validation_v13(
                api_key="offline-combined-v13-key",
                registry=FrozenH2MockRegistry(),
                transport_factory=transport_factory,
                authority=authority,
                output_parent=Path(temp),
                run_id="combined_prompt_v13_q04_offline_runner_test",
            )
            self.assertTrue(result.passed, result.summary)
            self.assertEqual(
                result.summary["question_ids_executed"], list(QUESTION_ORDER)
            )
            self.assertEqual(
                result.summary["actual_response_attempts"],
                EXPECTED_RESPONSES["Q04"],
            )
            self.assertEqual(result.summary["response_attempt_upper_bound"], RESPONSE_CAP)
            self.assertEqual(result.summary["semantic_correction_attempts"], 0)
            self.assertEqual(
                result.summary["tool_selection_prompt_version"],
                COMBINED_PROMPT_VERSION,
            )


if __name__ == "__main__":
    unittest.main()
