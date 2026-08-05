from __future__ import annotations

import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from scripts import run_q01_q10_batch_a_flash_validation as entry
from src.deepseek_client import (
    ChatCompletionResult,
    DeepSeekClientError,
    ProviderToolCall,
)
from src.mock_h2_registry import FrozenH2MockRegistry
from src.mock_native_tool_client_v2_1_revision import _tool_payloads
from src.native_tool_transport_mock_v2_1_revision import (
    OfflineNativeToolTransportV2_1Revision,
)
from src.online_native_tool_candidate_v2_1_revision import (
    ResponseLimitedStrictNativeClient,
)
from src.q01_q10_batch_a_offline_mock import (
    BatchAEvidenceCompleteMockClient,
)
from src.q01_q10_batch_a_safe_runner import (
    BATCH_A_OFFLINE_CONFIRMATION,
    BATCH_A_QUESTION_IDS,
    BATCH_A_REAL_CONFIRMATION,
    BatchASafeRunnerError,
    execute_batch_a_validation,
    validate_batch_a_runner_implementation,
    validate_offline_execution_request,
    validate_real_execution_request,
)


class FailAtTransport:
    def __init__(self, delegate, *, fail_at: int) -> None:
        self.delegate = delegate
        self.fail_at = fail_at
        self.attempted = 0

    def __call__(self, url, body, headers, timeout_seconds):
        self.attempted += 1
        if self.attempted == self.fail_at:
            raise DeepSeekClientError("offline injected network interruption")
        return self.delegate(url, body, headers, timeout_seconds)

    def audit_payload(self):
        payload = self.delegate.audit_payload()
        payload["injected_transport_attempts"] = self.attempted
        payload["injected_failure_at"] = self.fail_at
        return payload


class WrongQ06SecondArgumentsClient(BatchAEvidenceCompleteMockClient):
    def complete_strict_tools(self, **kwargs):
        result = super().complete_strict_tools(**kwargs)
        messages = kwargs["messages"]
        if len(_tool_payloads(messages)) != 1 or not result.tool_calls:
            return result
        call = result.tool_calls[0]
        if call.tool_name != "rank_products":
            return result
        arguments = dict(call.arguments)
        arguments["top_n"] = 4
        return ChatCompletionResult(
            finish_reason=result.finish_reason,
            content=result.content,
            tool_calls=(
                ProviderToolCall(
                    provider_call_id=call.provider_call_id,
                    tool_name=call.tool_name,
                    arguments=arguments,
                ),
            ),
            raw_response=result.raw_response,
            usage=result.usage,
        )


def _transport(client=None):
    return OfflineNativeToolTransportV2_1Revision(
        client or BatchAEvidenceCompleteMockClient(),
        expected_model="deepseek-v4-flash",
        terminal_question_ids=BATCH_A_QUESTION_IDS,
        terminal_json_question_ids=BATCH_A_QUESTION_IDS,
    )


def _offline_authority():
    return validate_offline_execution_request(
        confirmation=BATCH_A_OFFLINE_CONFIRMATION
    )


class BatchASafeRunnerTests(unittest.TestCase):
    def test_contract_and_offline_authority_are_exact(self) -> None:
        contract = validate_batch_a_runner_implementation()
        self.assertEqual(contract["scope"]["response_attempt_upper_bound"], 8)
        authority = _offline_authority()
        self.assertEqual(authority.mode, "offline_injected_transport")
        self.assertEqual(authority.question_ids, BATCH_A_QUESTION_IDS)
        with self.assertRaises(BatchASafeRunnerError):
            validate_offline_execution_request(
                approved_model_responses=9,
                confirmation=BATCH_A_OFFLINE_CONFIRMATION,
            )

    def test_real_entry_stops_before_api_key_read(self) -> None:
        args = Namespace(
            batch_id="A",
            question_id=list(BATCH_A_QUESTION_IDS),
            model="deepseek-v4-flash",
            approved_model_responses=8,
            automatic_retries=0,
            confirm_real_model_calls="I_AUTHORIZE_Q01_Q10_BATCH_A_FLASH_REAL_CALLS",
        )
        with patch.object(entry, "parse_args", return_value=args), patch.object(
            entry,
            "validate_real_execution_request",
            side_effect=BatchASafeRunnerError("offline denial probe"),
        ), patch.object(
            entry,
            "_load_api_key",
            side_effect=AssertionError("API key must not be read"),
        ):
            with self.assertRaisesRegex(SystemExit, "authorization gate"):
                entry.main()

    def test_crash_safe_real_revalidation_authority_is_exact_and_single_use(self) -> None:
        plan = json.loads(
            entry.PROJECT_ROOT.joinpath(
                "config",
                "h3_q01_q10_new_harness_flash_real_validation_plan.candidate.json",
            ).read_text(encoding="utf-8")
        )
        pending_auth = plan[
            "batch_a_crash_safe_real_revalidation_authorization"
        ]
        pending_auth["status"] = "authorized_pending_single_execution"
        pending_auth["consumed"] = False
        pending_auth["real_model_calls_allowed"] = True
        authority = validate_real_execution_request(
            batch_id="A",
            question_ids=BATCH_A_QUESTION_IDS,
            model="deepseek-v4-flash",
            approved_model_responses=8,
            automatic_retries=0,
            confirmation=BATCH_A_REAL_CONFIRMATION,
            plan=plan,
        )
        self.assertEqual(authority.mode, "real_transport")
        consumed = json.loads(json.dumps(plan))
        consumed_auth = consumed[
            "batch_a_crash_safe_real_revalidation_authorization"
        ]
        consumed_auth["status"] = "consumed"
        consumed_auth["consumed"] = True
        consumed_auth["real_model_calls_allowed"] = False
        with self.assertRaisesRegex(BatchASafeRunnerError, "unconsumed"):
            validate_real_execution_request(
                batch_id="A",
                question_ids=BATCH_A_QUESTION_IDS,
                model="deepseek-v4-flash",
                approved_model_responses=8,
                automatic_retries=0,
                confirmation=BATCH_A_REAL_CONFIRMATION,
                plan=consumed,
            )

    def _execute(self, transport, *, run_id: str):
        temporary = tempfile.TemporaryDirectory(
            dir=entry.PROJECT_ROOT / "results" / "raw"
        )
        self.addCleanup(temporary.cleanup)
        return execute_batch_a_validation(
            api_key=f"offline-{run_id}-secret",
            registry=FrozenH2MockRegistry(),
            transport=transport,
            authority=_offline_authority(),
            output_parent=Path(temporary.name),
            run_id=run_id,
        )

    def test_success_consumes_exactly_eight_and_saves_safe_evidence(self) -> None:
        transport = _transport()
        result = self._execute(transport, run_id="batch-a-success")
        self.assertTrue(result.passed)
        self.assertEqual(result.summary["actual_response_attempts"], 8)
        self.assertEqual(result.summary["completed_model_responses"], 8)
        self.assertEqual(
            result.summary["question_ids_executed"], list(BATCH_A_QUESTION_IDS)
        )
        self.assertEqual(result.summary["question_ids_not_executed"], [])
        self.assertEqual(len(transport.requests), 8)
        self.assertEqual(
            [request.tool_choice for request in transport.requests],
            ["auto", "none", "auto", "auto", "none", "none", "none", "none"],
        )
        self.assertEqual(
            [request.response_format_present for request in transport.requests],
            [False, True, False, False, True, True, True, True],
        )
        self.assertEqual(
            [request.max_tokens for request in transport.requests],
            [4096, 8192, 4096, 4096, 8192, 4096, 4096, 4096],
        )
        transport_audit = json.loads(
            (result.output_dir / "transport_audit.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            transport_audit["execution_mode"],
            "offline_injected_transport",
        )
        self.assertEqual(transport_audit["attempted"], 8)
        self.assertEqual(transport_audit["http_responses_received"], 8)
        self.assertEqual(transport_audit["parsed_responses"], 8)
        self.assertEqual(transport_audit["failed_attempts"], 0)
        self.assertFalse(transport_audit["real_network_opened"])
        self.assertFalse(transport_audit["real_model_response_received"])
        self.assertFalse(transport_audit["api_key_value_saved"])
        self.assertFalse(transport_audit["api_key_source_saved"])
        saved = "\n".join(
            path.read_text(encoding="utf-8")
            for path in result.output_dir.glob("*.json")
        )
        self.assertNotIn("offline-batch-a-success-secret", saved)
        self.assertNotIn('"Authorization"', saved)
        self.assertNotIn("Bearer ", saved)
        self.assertNotRegex(saved, r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]")
        self.assertFalse(result.summary["privacy_audit"]["raw_customer_id_exported"])

    def test_transport_failure_counts_once_and_stops_later_questions(self) -> None:
        base = _transport()
        transport = FailAtTransport(base, fail_at=3)
        result = self._execute(transport, run_id="batch-a-network-failure")
        self.assertFalse(result.passed)
        self.assertEqual(result.summary["actual_response_attempts"], 3)
        self.assertEqual(result.summary["completed_model_responses"], 2)
        self.assertEqual(result.summary["failed_transport_or_provider_attempts"], 1)
        self.assertEqual(result.summary["question_ids_executed"], ["Q02", "Q06"])
        self.assertEqual(
            result.summary["question_ids_not_executed"],
            ["Q08", "Q09", "Q10"],
        )
        failures = json.loads(
            (result.output_dir / "failed_attempts.json").read_text(encoding="utf-8")
        )
        self.assertEqual(len(failures), 1)
        self.assertTrue(failures[0]["transport_attempt_failed"])
        self.assertFalse(failures[0]["automatic_retry_performed"])

    def test_semantic_failure_stops_without_retry(self) -> None:
        result = self._execute(
            _transport(WrongQ06SecondArgumentsClient()),
            run_id="batch-a-semantic-failure",
        )
        self.assertFalse(result.passed)
        self.assertEqual(result.summary["actual_response_attempts"], 4)
        self.assertEqual(result.summary["completed_model_responses"], 4)
        self.assertEqual(result.summary["failed_transport_or_provider_attempts"], 0)
        self.assertEqual(result.summary["question_ids_executed"], ["Q02", "Q06"])
        self.assertFalse(result.summary["automatic_retry_performed"])

    def test_offline_authority_cannot_enable_real_transport(self) -> None:
        with tempfile.TemporaryDirectory(
            dir=entry.PROJECT_ROOT / "results" / "raw"
        ) as temporary:
            with self.assertRaises(BatchASafeRunnerError):
                execute_batch_a_validation(
                    api_key="offline-only-secret",
                    registry=FrozenH2MockRegistry(),
                    transport=None,
                    authority=_offline_authority(),
                    output_parent=Path(temporary),
                    run_id="offline-authority-no-real",
                )

    def test_ninth_attempt_is_blocked_before_underlying_client(self) -> None:
        class CountingClient:
            def __init__(self) -> None:
                self.calls = 0

            def complete_strict_tools(self, **kwargs):
                self.calls += 1
                return ChatCompletionResult(
                    finish_reason="stop",
                    content="{}",
                    tool_calls=(),
                    raw_response={"offline": True},
                    usage=None,
                )

        underlying = CountingClient()
        limited = ResponseLimitedStrictNativeClient(underlying, limit=8)
        for _ in range(8):
            limited.complete_strict_tools(messages=[], tools=[])
        with self.assertRaises(DeepSeekClientError):
            limited.complete_strict_tools(messages=[], tools=[])
        self.assertEqual(underlying.calls, 8)
        self.assertEqual(limited.snapshot().attempted, 8)


if __name__ == "__main__":
    unittest.main()
