from __future__ import annotations

import json
import unittest
from pathlib import Path

from src.agent_protocol import AgentProtocolError, parse_control_response
from src.deepseek_report_terminal_transport_mock_v2_3 import (
    FrozenNativeLogicalClientV2_3,
    OfflineDeepSeekProviderV2_3,
)
from src.deepseek_report_terminal_transport_v2_3 import (
    BETA_URL,
    STANDARD_URL,
)
from src.fixed_question_validation import (
    load_frozen_questions,
    validate_fixed_question,
)
from src.mock_h2_registry import FrozenH2MockRegistry
from src.mock_native_tool_client_v2_1_revision import (
    FrozenQuestionNativeToolMockClient,
)
from src.online_native_tool_candidate_v2_3 import (
    NativeToolOnlineCandidateV2_3,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAVED_Q02 = (
    PROJECT_ROOT
    / "results"
    / "raw"
    / "q01_q10_batch_a_flash_20260803T233810_455037+0800"
    / "Q02.json"
)
EXPECTED_RESPONSES = {
    "Q01": 2,
    "Q02": 2,
    "Q03": 2,
    "Q04": 2,
    "Q05": 3,
    "Q06": 3,
    "Q07": 3,
    "Q08": 1,
    "Q09": 1,
    "Q10": 1,
}


class DeepSeekReportTerminalSerializationV2_3Tests(unittest.TestCase):
    def _run(self, question_id: str):
        logical = FrozenNativeLogicalClientV2_3(
            FrozenQuestionNativeToolMockClient()
        )
        provider = OfflineDeepSeekProviderV2_3(logical)
        candidate = NativeToolOnlineCandidateV2_3(
            api_key="offline-v2-3-test-key",
            registry=FrozenH2MockRegistry(),
            response_limit=EXPECTED_RESPONSES[question_id],
            transport=provider,
        )
        outcome = candidate.run_turn(
            session_id=f"SESSION-v23-{question_id.lower()}",
            turn_id=f"TURN-{int(question_id[1:]):03d}",
            question=load_frozen_questions()[question_id]["question"],
            result_root="results/raw/v2_3_test_only",
        )
        return outcome, candidate, provider

    def test_q01_q10_use_beta_only_for_business_tools(self) -> None:
        total = 0
        for question_id, expected_count in EXPECTED_RESPONSES.items():
            with self.subTest(question_id=question_id):
                outcome, candidate, provider = self._run(question_id)
                self.assertIn(
                    validate_fixed_question(question_id, outcome).status,
                    {
                        "protocol_and_dataflow_passed",
                        "passed_deterministic_pending_manual_review",
                    },
                )
                self.assertEqual(len(provider.requests), expected_count)
                total += len(provider.requests)
                terminal = provider.requests[-1]
                self.assertEqual(terminal.endpoint, STANDARD_URL)
                self.assertEqual(terminal.tool_count, 0)
                self.assertFalse(terminal.tool_choice_present)
                self.assertEqual(
                    terminal.response_format,
                    {"type": "json_object"},
                )
                self.assertEqual(
                    terminal.max_tokens,
                    8192 if question_id <= "Q07" else 4096,
                )
                self.assertEqual(
                    candidate.last_trace[-1].visible_tool_names,
                    (),
                )
                self.assertNotIn("tool", terminal.message_roles)
                for keys in terminal.terminal_evidence_call_keys:
                    self.assertNotIn("result", keys)
                    self.assertNotIn("arguments", keys)
                    self.assertIn("facts", keys)
                for request in provider.requests[:-1]:
                    self.assertEqual(request.endpoint, BETA_URL)
                    self.assertEqual(request.tool_count, 7)
                    self.assertTrue(request.tool_choice_present)
                    self.assertEqual(request.tool_choice, "auto")
                    self.assertIsNone(request.response_format)
        self.assertEqual(total, 20)

    def test_saved_q02_dsml_failure_is_not_repaired(self) -> None:
        saved = json.loads(SAVED_Q02.read_text(encoding="utf-8"))
        content = saved["outcome"]["raw_responses"][1]["choices"][0][
            "message"
        ]["content"]
        self.assertIn("DSML", content)
        with self.assertRaises(AgentProtocolError):
            parse_control_response(content)

    def test_transport_audit_distinguishes_logical_and_wire_permissions(self) -> None:
        _, candidate, provider = self._run("Q02")
        logical = candidate.transport_audit_payload()["requests"]
        self.assertEqual([item["inbound_tool_count"] for item in logical], [7, 7])
        self.assertEqual([item["outbound_tool_count"] for item in logical], [7, 0])
        self.assertEqual([item["rewritten"] for item in logical], [False, True])
        self.assertEqual(logical[-1]["projected_tool_message_count"], 1)
        self.assertEqual(
            logical[-1]["removed_tool_payload_keys"],
            ("arguments", "result"),
        )
        self.assertEqual(
            logical[-1]["dropped_assistant_tool_call_messages"],
            1,
        )
        self.assertEqual(logical[-1]["outbound_tool_role_message_count"], 0)
        self.assertTrue(logical[-1]["terminal_evidence_envelope_added"])
        self.assertEqual(
            [item.endpoint for item in provider.requests],
            [BETA_URL, STANDARD_URL],
        )


if __name__ == "__main__":
    unittest.main()
