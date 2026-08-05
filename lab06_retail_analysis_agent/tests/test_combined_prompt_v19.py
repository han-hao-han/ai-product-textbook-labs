from __future__ import annotations

import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace

from src.terminal_protocol_disambiguation_v19 import (
    terminal_draft_issues_v19, terminal_protocol_issues_v19,
)
from src.combined_prompt_v19_real_runner import (
    execute_validation_v19_checkpoint, execute_validation_v19_full,
)
from src.deepseek_internal_call_isolation_transport_mock_v2_3_4_2 import (
    CallIsolatedFrozenQuestionNativeToolMockClient,
    CallIsolatedLogicalClientV2_3_4_2, OfflineDeepSeekProviderV2_3_4_2,
)
from src.mock_h2_registry import FrozenH2MockRegistry
from src.tool_routing_prompt_v1_real_runner import OFFLINE_CONFIRMATION, validate_offline_request


class CombinedPromptV19Tests(unittest.TestCase):
    def test_incomplete_period_fact_is_not_forced_into_narrative_slot(self) -> None:
        fact = SimpleNamespace(
            evidence_type="FACT", metric="incomplete_period", value="2011-12",
            display_value="2011-12", fact_id="FACT-007", rank=None,
            start_date=None, end_date=None, dimensions=[],
        )
        response = SimpleNamespace(report=SimpleNamespace(sections=[
            SimpleNamespace(claims=[]),
            SimpleNamespace(claims=[SimpleNamespace(statement="包含不完整期间提示。", evidence=[fact])]),
            *[SimpleNamespace(claims=[]) for _ in range(4)],
        ]))
        self.assertEqual(terminal_draft_issues_v19(response), [])

    def test_safe_slot_binding_failure_becomes_structured_feedback(self) -> None:
        issues = terminal_protocol_issues_v19(
            "slot_report_binding_validation",
            "SLOT-003 report section borrowed evidence from another slot", "{}",
        )
        self.assertEqual(issues[0]["location"], "SLOT-003")
        self.assertEqual(terminal_protocol_issues_v19("model_visible_internal_call_id", "unsafe", "{}"), [])

    def test_checkpoint_and_full_mock_runs_pass(self) -> None:
        authority = validate_offline_request(confirmation=OFFLINE_CONFIRMATION)
        def factory(_question_id: str):
            logical = CallIsolatedLogicalClientV2_3_4_2(CallIsolatedFrozenQuestionNativeToolMockClient())
            return OfflineDeepSeekProviderV2_3_4_2(logical)
        common = {
            "registry": FrozenH2MockRegistry(), "transport_factory": factory,
            "authority": authority,
        }
        with tempfile.TemporaryDirectory() as temp:
            checkpoint = execute_validation_v19_checkpoint(
                api_key="offline-v19-checkpoint", output_parent=Path(temp),
                run_id="v19_checkpoint_offline", **common,
            )
            full = execute_validation_v19_full(
                api_key="offline-v19-full", output_parent=Path(temp),
                run_id="v19_full_offline", **common,
            )
        self.assertTrue(checkpoint.passed, checkpoint.summary)
        self.assertTrue(full.passed, full.summary)


if __name__ == "__main__":
    unittest.main()
