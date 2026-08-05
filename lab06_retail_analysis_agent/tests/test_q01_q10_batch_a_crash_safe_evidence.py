from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from time import perf_counter

from src.deepseek_client import (
    ChatCompletionResult,
    DeepSeekClientError,
    HttpResponseData,
)
from src.mock_h2_registry import FrozenH2MockRegistry
from src.native_tool_transport_mock_v2_1_revision import (
    OfflineNativeToolTransportV2_1Revision,
)
from src.online_native_tool_candidate_v2_1_revision import (
    ResponseLimitedStrictNativeClient,
)
from src.q01_q10_batch_a_crash_safe_evidence import (
    BatchACrashSafeJournal,
    CrashSafeEvidenceError,
    load_crash_safe_evidence_boundary,
    recover_batch_a_run_state,
    validate_crash_safe_evidence_boundary,
)
from src.q01_q10_batch_a_offline_mock import (
    BatchAEvidenceCompleteMockClient,
)
from src.q01_q10_batch_a_safe_runner import (
    BATCH_A_OFFLINE_CONFIRMATION,
    BATCH_A_QUESTION_IDS,
    BATCH_A_REQUEST_TIMEOUT_SECONDS,
    BATCH_A_TOTAL_TIMEOUT_SECONDS,
    execute_batch_a_validation,
    validate_offline_execution_request,
)


class SimulatedExternalTermination(BaseException):
    pass


class TerminatingTransport:
    def __call__(self, url, body, headers, timeout_seconds):
        raise SimulatedExternalTermination("simulated process termination")


class InvalidJsonTransport:
    def __call__(self, url, body, headers, timeout_seconds):
        return HttpResponseData(status_code=200, content=b"not-json")


def _authority():
    return validate_offline_execution_request(
        confirmation=BATCH_A_OFFLINE_CONFIRMATION
    )


class BatchACrashSafeEvidenceTests(unittest.TestCase):
    def _temporary_parent(self):
        temporary = tempfile.TemporaryDirectory(
            dir=Path(__file__).resolve().parents[1] / "results" / "raw"
        )
        self.addCleanup(temporary.cleanup)
        return Path(temporary.name)

    def test_contract_freezes_time_persistence_and_no_resume(self) -> None:
        contract = validate_crash_safe_evidence_boundary()
        self.assertEqual(
            contract["status"],
            "frozen_by_user_offline_validated_pending_new_real_authorization",
        )
        self.assertEqual(
            contract["time_boundaries"]["batch_internal_timeout_seconds"],
            1080,
        )
        self.assertFalse(contract["recovery"]["automatic_resume_allowed"])
        self.assertTrue(
            contract["user_freeze"]["freeze_does_not_authorize_real_calls"]
        )
        drifted = deepcopy(load_crash_safe_evidence_boundary())
        drifted["time_boundaries"]["batch_internal_timeout_seconds"] = 120
        with self.assertRaises(CrashSafeEvidenceError):
            validate_crash_safe_evidence_boundary(drifted)

    def test_frozen_boundary_cannot_restore_authority_or_auto_resume(self) -> None:
        drifted = deepcopy(load_crash_safe_evidence_boundary())
        drifted["user_freeze"]["automatic_resume_allowed"] = True
        with self.assertRaises(CrashSafeEvidenceError):
            validate_crash_safe_evidence_boundary(drifted)

        drifted = deepcopy(load_crash_safe_evidence_boundary())
        drifted["user_freeze"][
            "freeze_does_not_restore_consumed_authorization"
        ] = False
        with self.assertRaises(CrashSafeEvidenceError):
            validate_crash_safe_evidence_boundary(drifted)

    def test_external_termination_preserves_reserved_attempt(self) -> None:
        parent = self._temporary_parent()
        run_id = "crash-after-reservation"
        with self.assertRaises(SimulatedExternalTermination):
            execute_batch_a_validation(
                api_key="offline-crash-reservation-secret",
                registry=FrozenH2MockRegistry(),
                transport=TerminatingTransport(),
                authority=_authority(),
                output_parent=parent,
                run_id=run_id,
            )
        recovery = recover_batch_a_run_state(parent / run_id)
        self.assertEqual(recovery["current_question_id"], "Q02")
        self.assertEqual(recovery["reserved_attempts"], 1)
        self.assertEqual(recovery["http_responses_received"], 0)
        self.assertEqual(recovery["parsed_responses"], 0)
        self.assertTrue(recovery["authorization_consumed"])
        self.assertFalse(recovery["automatic_resume_allowed"])
        self.assertTrue(recovery["recovery_requires_new_user_authorization"])

    def test_http_body_is_persisted_before_json_parse_failure(self) -> None:
        parent = self._temporary_parent()
        run_id = "http-before-parse"
        result = execute_batch_a_validation(
            api_key="offline-http-parse-secret",
            registry=FrozenH2MockRegistry(),
            transport=InvalidJsonTransport(),
            authority=_authority(),
            output_parent=parent,
            run_id=run_id,
        )
        self.assertFalse(result.passed)
        recovery = recover_batch_a_run_state(parent / run_id)
        self.assertEqual(recovery["reserved_attempts"], 1)
        self.assertEqual(recovery["http_responses_received"], 1)
        self.assertEqual(recovery["parsed_responses"], 0)
        raw_path = parent / run_id / recovery["raw_http_response_files"][0]
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        self.assertEqual(raw["content_base64"], "bm90LWpzb24=")

    def test_complete_batch_has_eight_atomic_response_checkpoints(self) -> None:
        parent = self._temporary_parent()
        run_id = "crash-safe-success"
        transport = OfflineNativeToolTransportV2_1Revision(
            BatchAEvidenceCompleteMockClient(),
            expected_model="deepseek-v4-flash",
            terminal_question_ids=BATCH_A_QUESTION_IDS,
            terminal_json_question_ids=BATCH_A_QUESTION_IDS,
        )
        result = execute_batch_a_validation(
            api_key="offline-crash-safe-success-secret",
            registry=FrozenH2MockRegistry(),
            transport=transport,
            authority=_authority(),
            output_parent=parent,
            run_id=run_id,
        )
        self.assertTrue(result.passed)
        recovery = recover_batch_a_run_state(parent / run_id)
        self.assertEqual(recovery["reserved_attempts"], 8)
        self.assertEqual(recovery["http_responses_received"], 8)
        self.assertEqual(recovery["parsed_responses"], 8)
        self.assertEqual(len(recovery["raw_http_response_files"]), 8)
        self.assertEqual(len(recovery["parsed_response_files"]), 8)
        self.assertFalse(list((parent / run_id).rglob("*.tmp")))

    def test_batch_deadline_stops_before_attempt_and_transport(self) -> None:
        events = []

        class CountingClient:
            timeout_seconds = 120.0

            def __init__(self) -> None:
                self.calls = 0
                self.response_event_sink = None

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
        limited = ResponseLimitedStrictNativeClient(
            underlying,
            limit=8,
            response_event_sink=lambda kind, payload: events.append(
                (kind, payload)
            ),
            batch_timeout_seconds=1.0,
            started_monotonic=perf_counter() - 2.0,
        )
        with self.assertRaisesRegex(DeepSeekClientError, "batch deadline"):
            limited.complete_strict_tools(messages=[], tools=[])
        self.assertEqual(underlying.calls, 0)
        self.assertEqual(limited.snapshot().attempted, 0)
        self.assertEqual(events[0][0], "batch_deadline_reached")

    def test_time_boundary_has_full_batch_headroom(self) -> None:
        self.assertEqual(BATCH_A_REQUEST_TIMEOUT_SECONDS, 120.0)
        self.assertEqual(BATCH_A_TOTAL_TIMEOUT_SECONDS, 1080.0)
        self.assertGreaterEqual(
            BATCH_A_TOTAL_TIMEOUT_SECONDS,
            8 * BATCH_A_REQUEST_TIMEOUT_SECONDS + 120,
        )

    def test_journal_never_persists_secret_or_absolute_path(self) -> None:
        parent = self._temporary_parent()
        run_dir = parent / "journal-safety"
        secret = "offline-journal-safety-secret"
        journal = BatchACrashSafeJournal(
            output_dir=run_dir,
            run_id="journal-safety",
            secret=secret,
            execution_mode="offline_injected_transport",
            question_ids=BATCH_A_QUESTION_IDS,
            model="deepseek-v4-flash",
            response_attempt_upper_bound=8,
            automatic_retry_count=0,
            request_timeout_seconds=120,
            batch_timeout_seconds=1080,
        )
        journal.initialize()
        journal.question_started("Q02")
        journal.response_event(
            "attempt_reserved",
            {
                "attempt_index": 1,
                "remaining_batch_seconds": 1080,
                "effective_request_timeout_seconds": 120,
            },
        )
        saved = "\n".join(
            path.read_text(encoding="utf-8")
            for path in run_dir.rglob("*.json")
        )
        self.assertNotIn(secret, saved)
        self.assertNotIn('"Authorization"', saved)
        self.assertNotIn("Bearer ", saved)
        self.assertNotRegex(saved, r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]")


if __name__ == "__main__":
    unittest.main()
