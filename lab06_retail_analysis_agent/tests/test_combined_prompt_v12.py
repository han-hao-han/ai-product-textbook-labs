from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.combined_prompt_v12_real_runner import (
    QUESTION_ORDER,
    RESPONSE_CAP,
    execute_validation_v12,
)
from src.deepseek_internal_call_isolation_transport_mock_v2_3_4_2 import (
    CallIsolatedFrozenQuestionNativeToolMockClient,
    CallIsolatedLogicalClientV2_3_4_2,
    OfflineDeepSeekProviderV2_3_4_2,
)
from src.mock_h2_registry import FrozenH2MockRegistry
from src.online_native_tool_candidate_combined_v12 import COMBINED_PROMPT_VERSION
from src.report_validation import ReportFactReference, ReportRequestReference
from src.terminal_slot2_forbidden_v12 import slot2_forbidden_literals_v12
from src.tool_routing_prompt_v1_real_runner import (
    OFFLINE_CONFIRMATION,
    validate_offline_request,
)


class CombinedPromptV12Tests(unittest.TestCase):
    def test_incomplete_and_excluded_period_literals_are_deduplicated(self) -> None:
        references = [
            ReportFactReference(
                fact_id="FACT-001", metric="incomplete_period",
                value="2011-12", display_value="2011-12",
                unit="calendar_month", rank=None, dimensions=[],
                period="complete_months_only", start_date=None, end_date=None,
            ),
            ReportRequestReference(
                evidence_type="REQUEST", request_id="REQUEST-001",
                parameter_name="excluded_period", value="2011-12",
                source="validated_user_input",
            ),
        ]
        self.assertEqual(slot2_forbidden_literals_v12(references), ["2011-12"])

    def test_q04_checkpoint_passes_offline(self) -> None:
        authority = validate_offline_request(confirmation=OFFLINE_CONFIRMATION)

        def transport_factory(_question_id: str):
            logical = CallIsolatedLogicalClientV2_3_4_2(
                CallIsolatedFrozenQuestionNativeToolMockClient()
            )
            return OfflineDeepSeekProviderV2_3_4_2(logical)

        with tempfile.TemporaryDirectory() as temp:
            result = execute_validation_v12(
                api_key="offline-combined-v12-key",
                registry=FrozenH2MockRegistry(),
                transport_factory=transport_factory,
                authority=authority,
                output_parent=Path(temp),
                run_id="combined_prompt_v12_q04_offline_runner_test",
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
