from __future__ import annotations

import json
import unittest

from src.deepseek_internal_call_isolation_transport_mock_v2_3_4_2 import (
    CallIsolatedFrozenQuestionNativeToolMockClient,
    CallIsolatedLogicalClientV2_3_4_2,
    OfflineDeepSeekProviderV2_3_4_2,
)
from src.deepseek_client import DeepSeekClientError
from src.deepseek_internal_call_isolation_transport_v2_3_4_2 import (
    ModelVisibleCallIsolationTransportV2_3_4_2,
)
from src.fixed_question_validation import (
    load_frozen_questions,
    validate_fixed_question,
)
from src.mock_h2_registry import FrozenH2MockRegistry
from src.online_native_tool_candidate_v2_3_4_2 import (
    NativeToolOnlineCandidateV2_3_4_2,
)
from src.report_terminal_protocol_guard_v2_3_4_2 import (
    model_control_response_schema_v2_3_4_2,
)


EXPECTED_RESPONSES = {
    "Q01": 3,
    "Q02": 3,
    "Q03": 3,
    "Q04": 3,
    "Q05": 4,
    "Q06": 4,
    "Q07": 4,
    "Q08": 1,
    "Q09": 1,
    "Q10": 1,
}


def _candidate(
    question_id: str, *, selection_mutator=None, report_mutator=None
):
    logical = CallIsolatedLogicalClientV2_3_4_2(
        CallIsolatedFrozenQuestionNativeToolMockClient(),
        selection_mutator=selection_mutator,
        report_mutator=report_mutator,
    )
    provider = OfflineDeepSeekProviderV2_3_4_2(logical)
    candidate = NativeToolOnlineCandidateV2_3_4_2(
        api_key="offline-v2342-key",
        registry=FrozenH2MockRegistry(),
        response_limit=EXPECTED_RESPONSES[question_id],
        transport=provider,
    )
    return candidate, provider


class ReportTerminalProtocolGuardV2_3_4_2Tests(unittest.TestCase):
    def _run(self, question_id: str, **kwargs):
        candidate, provider = _candidate(question_id, **kwargs)
        outcome = candidate.run_turn(
            session_id=f"SESSION-v2342-{question_id.lower()}",
            turn_id=f"TURN-{int(question_id[1:]):03d}",
            question=load_frozen_questions()[question_id]["question"],
            result_root="results/raw/v2_3_4_2_protocol_guard_test",
        )
        return candidate, provider, outcome

    def test_model_visible_control_schema_has_no_internal_call_field(self) -> None:
        serialized = json.dumps(
            model_control_response_schema_v2_3_4_2(),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        self.assertNotIn("call_id", serialized)
        self.assertNotRegex(serialized, r"CALL-\d{3,}")
        self.assertIn("chart_source_key", serialized)

    def test_outbound_leak_is_audited_before_transport_stops(self) -> None:
        def delegate(*_args, **_kwargs):
            self.fail("leaking request must not reach the provider")

        transport = ModelVisibleCallIsolationTransportV2_3_4_2(delegate)
        body = json.dumps(
            {
                "messages": [
                    {"role": "user", "content": "forbidden CALL-999"}
                ]
            }
        ).encode("utf-8")
        with self.assertRaisesRegex(
            DeepSeekClientError, "model_visible_internal_call_id"
        ):
            transport("https://offline.invalid", body, {}, 1.0)
        audit = transport.audit_payload()
        self.assertFalse(
            audit["all_model_visible_internal_call_counts_zero"]
        )
        self.assertEqual(audit["model_visible_internal_call_values"], 1)
        self.assertEqual(audit["requests"][0]["model_visible_internal_call_values"], 1)

    def test_q01_q10_mock_end_to_end_and_wire_visibility(self) -> None:
        for question_id, expected in EXPECTED_RESPONSES.items():
            with self.subTest(question_id=question_id):
                candidate, provider, outcome = self._run(question_id)
                fixed = validate_fixed_question(question_id, outcome)
                self.assertEqual(
                    fixed.status,
                    "passed_deterministic_pending_manual_review",
                    fixed.issues,
                )
                snapshot = candidate.response_limit_snapshot()
                self.assertEqual(
                    (snapshot.attempted, snapshot.completed, snapshot.failed),
                    (expected, expected, 0),
                )
                self.assertEqual(len(provider.requests), expected)
                visibility = candidate.transport_audit_payload()[
                    "model_visibility"
                ]
                self.assertTrue(
                    visibility["all_model_visible_internal_call_counts_zero"]
                )
                self.assertTrue(
                    all(
                        item["model_visible_internal_call_values"] == 0
                        for item in visibility["requests"]
                    )
                )
                if question_id <= "Q07":
                    self.assertEqual(
                        candidate.atom_selection_trace[0].status, "passed"
                    )
                    self.assertEqual(
                        candidate.terminal_protocol_trace[0]["status"], "passed"
                    )
                    raw_payload = candidate.terminal_protocol_trace[0][
                        "parsed_model_response"
                    ]
                    mapped_payload = candidate.terminal_protocol_trace[0][
                        "mapped_program_response"
                    ]
                    self.assertNotIn(
                        "call_id", json.dumps(raw_payload, ensure_ascii=False)
                    )
                    if raw_payload["chart_requests"]:
                        self.assertIn(
                            "chart_source_key", raw_payload["chart_requests"][0]
                        )
                        self.assertIn("call_id", mapped_payload["chart_requests"][0])
                else:
                    self.assertEqual(candidate.terminal_protocol_trace, ())

    def test_multi_tool_turn_strips_nested_internal_fields(self) -> None:
        candidate, _, outcome = self._run("Q06")
        self.assertEqual(outcome.status, "completed")
        visibility = candidate.transport_audit_payload()["model_visibility"]
        removed = [
            path
            for request in visibility["requests"]
            for path in request["removed_internal_field_paths"]
        ]
        self.assertTrue(any(path.endswith("internal_call_id") for path in removed))
        self.assertTrue(any(path.endswith("call_id") for path in removed))
        self.assertTrue(any(path.endswith("source_result_path") for path in removed))

    def test_unknown_chart_source_alias_fails_before_formal_validator(self) -> None:
        def mutate(payload):
            payload["chart_requests"][0]["chart_source_key"] = "source_unknown"
            return payload

        candidate, _, outcome = self._run("Q02", report_mutator=mutate)
        self.assertEqual(outcome.status, "failed")
        self.assertEqual(outcome.error_stage, "terminal_protocol_validation")
        self.assertEqual(
            candidate.terminal_protocol_trace[0]["error_code"],
            "unknown_chart_source_alias",
        )
        self.assertIsNone(
            candidate.terminal_protocol_trace[0]["mapped_program_response"]
        )

    def test_chart_alias_tool_mismatch_fails_closed(self) -> None:
        def mutate(payload):
            payload["chart_requests"][0]["chart_type"] = "monthly_line"
            return payload

        candidate, _, outcome = self._run("Q02", report_mutator=mutate)
        self.assertEqual(outcome.error_stage, "terminal_protocol_validation")
        self.assertEqual(
            candidate.terminal_protocol_trace[0]["error_code"],
            "chart_source_alias_tool_mismatch",
        )

    def test_hallucinated_call_id_is_rejected(self) -> None:
        def mutate(payload):
            payload["report"]["sections"][2]["claims"][0][
                "statement"
            ] += " CALL-999"
            return payload

        candidate, _, outcome = self._run("Q02", report_mutator=mutate)
        self.assertEqual(outcome.error_stage, "terminal_protocol_validation")
        self.assertEqual(
            candidate.terminal_protocol_trace[0]["error_code"],
            "model_visible_internal_call_id",
        )

    def test_chart_source_alias_is_not_report_prose(self) -> None:
        def mutate(payload):
            payload["report"]["sections"][2]["claims"][0][
                "statement"
            ] += " source_alpha"
            return payload

        candidate, _, outcome = self._run("Q02", report_mutator=mutate)
        self.assertEqual(outcome.error_stage, "terminal_protocol_validation")
        self.assertEqual(
            candidate.terminal_protocol_trace[0]["error_code"],
            "chart_source_alias_in_report_prose",
        )

    def test_chart_source_alias_is_not_chart_title(self) -> None:
        def mutate(payload):
            alias = payload["chart_requests"][0]["chart_source_key"]
            payload["chart_requests"][0]["title"] += f" {alias}"
            return payload

        candidate, _, outcome = self._run("Q02", report_mutator=mutate)
        self.assertEqual(outcome.error_stage, "terminal_protocol_validation")
        self.assertEqual(
            candidate.terminal_protocol_trace[0]["error_code"],
            "chart_source_alias_in_report_prose",
        )

    def test_cross_turn_alias_registry_use_is_rejected(self) -> None:
        def mutate(payload):
            payload["report"]["turn_id"] = "TURN-999"
            return payload

        candidate, _, outcome = self._run("Q02", report_mutator=mutate)
        self.assertEqual(outcome.error_stage, "terminal_protocol_validation")
        self.assertEqual(
            candidate.terminal_protocol_trace[0]["error_code"],
            "cross_turn_chart_source_alias",
        )

    def test_alias_from_another_turn_is_unknown_in_current_registry(self) -> None:
        first_candidate, _, first_outcome = self._run("Q02")
        self.assertEqual(first_outcome.status, "completed")
        old_alias = first_candidate.terminal_protocol_trace[0][
            "parsed_model_response"
        ]["chart_requests"][0]["chart_source_key"]

        def mutate(payload):
            payload["chart_requests"][0]["chart_source_key"] = old_alias
            return payload

        candidate, _ = _candidate("Q02", report_mutator=mutate)
        outcome = candidate.run_turn(
            session_id="SESSION-v2342-q02-next",
            turn_id="TURN-003",
            question=load_frozen_questions()["Q02"]["question"],
            result_root="results/raw/v2_3_4_2_protocol_guard_test",
        )
        self.assertEqual(outcome.error_stage, "terminal_protocol_validation")
        self.assertEqual(
            candidate.terminal_protocol_trace[0]["error_code"],
            "unknown_chart_source_alias",
        )

    def test_rank_one_cannot_justify_items_per_order_one(self) -> None:
        def mutate(payload):
            payload["report"]["sections"][1]["claims"][0]["statement"] = (
                "该商品销量与订单数均为706，因此每单平均销量为1件。"
            )
            return payload

        candidate, _, outcome = self._run("Q02", report_mutator=mutate)
        self.assertEqual(outcome.error_stage, "terminal_protocol_validation")
        self.assertEqual(
            candidate.terminal_protocol_trace[0]["error_code"],
            "unsupported_derived_metric_intent",
        )
        self.assertIsNotNone(
            candidate.terminal_protocol_trace[0]["mapped_program_response"]
        )

    def test_rank_one_cannot_justify_unlabeled_derived_one_item(self) -> None:
        def mutate(payload):
            payload["report"]["sections"][1]["claims"][0]["statement"] = (
                "销量与订单数均为706，计算后的数值为1件。"
            )
            return payload

        candidate, _, outcome = self._run("Q02", report_mutator=mutate)
        self.assertEqual(outcome.error_stage, "terminal_protocol_validation")
        self.assertEqual(
            candidate.terminal_protocol_trace[0]["error_code"],
            "ambiguous_numeric_role_collision",
        )

    def test_structural_slot_failure_precedes_arithmetic_failure(self) -> None:
        def mutate(payload):
            payload["report"]["sections"][1]["claims"][0]["statement"] = (
                "每单平均销量为1件。"
            )
            borrowed = payload["report"]["sections"][5]["claims"][0][
                "evidence"
            ][0]
            payload["report"]["sections"][1]["claims"][0][
                "evidence"
            ].append(borrowed)
            return payload

        candidate, _, outcome = self._run("Q02", report_mutator=mutate)
        self.assertEqual(outcome.error_stage, "terminal_protocol_validation")
        self.assertEqual(
            candidate.terminal_protocol_trace[0]["error_code"],
            "slot_report_binding_validation",
        )

    def test_generic_share_without_direct_share_fact_is_rejected(self) -> None:
        def mutate(payload):
            payload["report"]["sections"][1]["claims"][0]["statement"] = (
                "该商品销售占比为1%。"
            )
            return payload

        candidate, _, outcome = self._run("Q02", report_mutator=mutate)
        self.assertEqual(outcome.error_stage, "terminal_protocol_validation")
        self.assertEqual(
            candidate.terminal_protocol_trace[0]["error_code"],
            "derived_metric_fact_missing",
        )

    def test_direct_share_fact_remains_allowed(self) -> None:
        def mutate(payload):
            claims = payload["report"]["sections"][1]["claims"]
            claim = next(
                item
                for item in claims
                if any(
                    evidence.get("metric") == "sales_amount_share"
                    for evidence in item["evidence"]
                )
            )
            fact = next(
                evidence
                for evidence in claim["evidence"]
                if evidence.get("metric") == "sales_amount_share"
            )
            claim["statement"] = f"该分组销售额占比为{fact['display_value']}。"
            claim["evidence"] = [fact]
            return payload

        candidate, _, outcome = self._run("Q05", report_mutator=mutate)
        self.assertEqual(outcome.status, "completed", outcome.error_message)
        self.assertEqual(candidate.terminal_protocol_trace[0]["status"], "passed")

    def test_direct_average_order_value_fact_remains_allowed(self) -> None:
        def mutate(payload):
            claim = payload["report"]["sections"][1]["claims"][0]
            fact = next(
                item
                for item in claim["evidence"]
                if item.get("metric") == "average_order_value"
            )
            claim["statement"] = f"客单价为{fact['display_value']}。"
            claim["evidence"] = [fact]
            return payload

        candidate, _, outcome = self._run("Q01", report_mutator=mutate)
        self.assertEqual(outcome.status, "completed", outcome.error_message)
        self.assertEqual(candidate.terminal_protocol_trace[0]["status"], "passed")

    def test_raw_direct_values_without_derived_intent_remain_allowed(self) -> None:
        def mutate(payload):
            claim = payload["report"]["sections"][1]["claims"][0]
            quantity = next(
                item
                for item in claim["evidence"]
                if item.get("metric") == "sales_quantity"
            )
            orders = next(
                item
                for item in claim["evidence"]
                if item.get("metric") == "order_count"
            )
            claim["statement"] = (
                f"销量为{quantity['display_value']}，订单数为{orders['display_value']}。"
            )
            claim["evidence"] = [quantity, orders]
            return payload

        candidate, _, outcome = self._run("Q02", report_mutator=mutate)
        self.assertEqual(outcome.status, "completed", outcome.error_message)
        self.assertEqual(candidate.terminal_protocol_trace[0]["status"], "passed")


if __name__ == "__main__":
    unittest.main()
