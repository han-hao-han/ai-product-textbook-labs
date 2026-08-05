from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.combined_prompt_v14_real_runner import (
    QUESTION_ORDER,
    RESPONSE_CAP,
    execute_validation_v14,
)
from src.deepseek_internal_call_isolation_transport_mock_v2_3_4_2 import (
    CallIsolatedFrozenQuestionNativeToolMockClient,
    CallIsolatedLogicalClientV2_3_4_2,
    OfflineDeepSeekProviderV2_3_4_2,
)
from src.mock_h2_registry import FrozenH2MockRegistry
from src.online_native_tool_candidate_combined_v14 import (
    COMBINED_PROMPT_VERSION,
    validate_combined_v14_real_authorization,
)
from src.online_native_tool_candidate_v2_1_revision import (
    NATIVE_REAL_MODEL_CONFIRMATION,
)
from src.terminal_protocol_feedback_v14 import terminal_protocol_issues_v14
from src.tool_routing_prompt_v1_real_runner import (
    EXPECTED_RESPONSES,
    OFFLINE_CONFIRMATION,
    validate_offline_request,
)


class CombinedPromptV14Tests(unittest.TestCase):
    def test_v14_real_gate_allows_only_two_extra_responses_per_question(self) -> None:
        validate_combined_v14_real_authorization(
            confirmation=NATIVE_REAL_MODEL_CONFIRMATION,
            approved_model_responses=6,
            question_count=1,
        )
        with self.assertRaisesRegex(ValueError, "too broad"):
            validate_combined_v14_real_authorization(
                confirmation=NATIVE_REAL_MODEL_CONFIRMATION,
                approved_model_responses=7,
                question_count=1,
            )

    def test_schema_feedback_identifies_missing_claim_evidence(self) -> None:
        payload = {
            "response_type": "report",
            "report": {
                "schema_version": "1.5.6-h3-report-draft-v1",
                "session_id": "SESSION-test",
                "turn_id": "TURN-004",
                "title": "test",
                "sections": [
                    {"name": name, "claims": [{"statement": "test"}]}
                    for name in (
                        "用户问题与分析口径", "关键经营发现", "工具证据与图表",
                        "有限解释", "经营建议", "数据与分析限制",
                    )
                ],
            },
            "chart_requests": [],
        }
        issues = terminal_protocol_issues_v14(
            "model_terminal_schema_invalid", "schema invalid",
            json.dumps(payload, ensure_ascii=False),
        )
        evidence_issues = [
            item for item in issues if item["location"].endswith("evidence")
        ]
        self.assertEqual(len(evidence_issues), 6)
        self.assertTrue(all(item["validation_type"] == "missing" for item in evidence_issues))
        self.assertEqual(
            terminal_protocol_issues_v14(
                "model_visible_internal_call_id", "security", "{}"
            ),
            [],
        )

    def test_q04_runner_accepts_baseline_with_two_unused_allowances(self) -> None:
        authority = validate_offline_request(confirmation=OFFLINE_CONFIRMATION)

        def transport_factory(_question_id: str):
            logical = CallIsolatedLogicalClientV2_3_4_2(
                CallIsolatedFrozenQuestionNativeToolMockClient()
            )
            return OfflineDeepSeekProviderV2_3_4_2(logical)

        with tempfile.TemporaryDirectory() as temp:
            result = execute_validation_v14(
                api_key="offline-combined-v14-key",
                registry=FrozenH2MockRegistry(),
                transport_factory=transport_factory,
                authority=authority,
                output_parent=Path(temp),
                run_id="combined_prompt_v14_q04_offline_runner_test",
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
