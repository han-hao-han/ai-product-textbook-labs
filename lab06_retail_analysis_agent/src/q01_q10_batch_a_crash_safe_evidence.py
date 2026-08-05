"""Atomic per-response evidence journal for batch-A validation."""

from __future__ import annotations

import base64
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = (
    PROJECT_ROOT
    / "config"
    / "h3_q01_q10_batch_a_crash_safe_evidence_boundary.json"
)
INCIDENT_PATH = (
    PROJECT_ROOT
    / "results"
    / "raw"
    / "q01_q10_batch_a_flash_real_interrupted_20260803T191246_162141+0800"
    / "summary.json"
)


class CrashSafeEvidenceError(ValueError):
    """Raised when crash-safe evidence cannot be stored safely."""


def _now() -> str:
    return datetime.now().astimezone().isoformat()


def _safe_text(value: Any, *, secret: str) -> str:
    text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if secret and secret in text:
        raise CrashSafeEvidenceError("refusing to persist API key material")
    if '"Authorization"' in text or "Bearer " in text:
        raise CrashSafeEvidenceError(
            "refusing to persist authorization header material"
        )
    if re.search(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]", text):
        raise CrashSafeEvidenceError(
            "refusing to persist local absolute paths"
        )
    return text


def _atomic_write_json(path: Path, value: Any, *, secret: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(_safe_text(value, secret=secret), encoding="utf-8")
    temporary.replace(path)


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CrashSafeEvidenceError(f"JSON object required: {path.name}")
    return value


def load_crash_safe_evidence_boundary() -> dict[str, Any]:
    return _read_object(CONTRACT_PATH)


def validate_crash_safe_evidence_boundary(
    contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    value = contract or load_crash_safe_evidence_boundary()
    if value.get("status") not in {
        "offline_implementation_pending_validation",
        "offline_implementation_validated_pending_user_checkpoint",
        "frozen_by_user_offline_validated_pending_new_real_authorization",
    }:
        raise CrashSafeEvidenceError("unexpected crash-safe boundary status")
    prerequisite = value.get("prerequisite", {})
    incident = _read_object(INCIDENT_PATH)
    if (
        incident.get("run_id") != prerequisite.get("interrupted_run_id")
        or incident.get("status") != prerequisite.get("interrupted_status")
        or prerequisite.get("offline_reinforcement_authorized_by_user") is not True
        or prerequisite.get("real_model_calls_authorized") is not False
    ):
        raise CrashSafeEvidenceError("crash-safe prerequisite drifted")
    scope = value.get("scope", {})
    if (
        scope.get("batch_id") != "A"
        or scope.get("question_ids")
        != ["Q02", "Q06", "Q08", "Q09", "Q10"]
        or scope.get("model") != "deepseek-v4-flash"
        or scope.get("response_attempt_upper_bound") != 8
        or scope.get("automatic_retry_count") != 0
        or any(
            scope.get(field) is not False
            for field in (
                "prompt_changed",
                "schema_changed",
                "h2_reference_answers_changed",
                "new_harness_acceptance_changed",
                "v2_2_3_resumed",
            )
        )
    ):
        raise CrashSafeEvidenceError("crash-safe scope drifted")
    time_boundary = value.get("time_boundaries", {})
    if (
        time_boundary.get("per_request_timeout_seconds") != 120
        or time_boundary.get("batch_internal_timeout_seconds") != 1080
        or time_boundary.get("eight_request_maximum_seconds") != 960
        or time_boundary.get("local_processing_headroom_seconds") != 120
        or time_boundary.get("external_process_timeout_must_exceed_seconds")
        != 1080
        or time_boundary.get("recommended_external_process_timeout_seconds")
        != 1200
        or time_boundary.get("remaining_batch_time_caps_each_request_timeout")
        is not True
        or time_boundary.get("batch_deadline_before_attempt_does_not_consume_attempt")
        is not True
    ):
        raise CrashSafeEvidenceError("time boundary drifted")
    if value.get("persistence_order") != [
        "atomic_attempt_reserved_event_before_transport",
        "atomic_raw_http_response_before_json_parse",
        "atomic_parsed_provider_response_after_parse",
        "atomic_question_checkpoint_after_new_harness",
        "atomic_batch_checkpoint_after_summary",
    ]:
        raise CrashSafeEvidenceError("persistence order drifted")
    recovery = value.get("recovery", {})
    if (
        recovery.get("read_only_audit_only") is not True
        or recovery.get("automatic_resume_allowed") is not False
        or recovery.get("new_user_authorization_required") is not True
        or recovery.get("reserved_attempt_consumes_authorization") is not True
        or recovery.get("unknown_provider_state_is_not_model_success_or_failure")
        is not True
    ):
        raise CrashSafeEvidenceError("recovery boundary drifted")
    privacy = value.get("privacy", {})
    if (
        privacy.get("http_response_body_saved_as_base64") is not True
        or any(
            privacy.get(field) is not False
            for field in (
                "api_key_saved",
                "authorization_header_value_saved",
                "request_headers_saved",
                "request_body_saved",
                "raw_customer_id_exported",
                "local_absolute_paths_saved",
            )
        )
    ):
        raise CrashSafeEvidenceError("crash-safe privacy boundary drifted")
    if value.get("status") in {
        "offline_implementation_validated_pending_user_checkpoint",
        "frozen_by_user_offline_validated_pending_new_real_authorization",
    }:
        offline = value.get("offline_validation", {})
        evidence_path = PROJECT_ROOT / str(offline.get("evidence_path", ""))
        if (
            offline.get("status") != "passed"
            or offline.get("reservation_survives_external_termination") is not True
            or offline.get("raw_http_survives_parse_failure") is not True
            or offline.get("success_reserved_received_parsed_counts")
            != {"reserved": 8, "http_received": 8, "parsed": 8}
            or offline.get("deadline_stops_before_attempt") is not True
            or offline.get("automatic_resume_allowed") is not False
            or offline.get("evidence_safety_passed") is not True
            or offline.get("real_network_opened") is not False
            or offline.get("real_model_called") is not False
            or offline.get("api_key_read") is not False
            or not evidence_path.is_file()
        ):
            raise CrashSafeEvidenceError("crash-safe offline evidence drifted")
        saved = _read_object(evidence_path)
        if (
            saved.get("run_id") != offline.get("run_id")
            or saved.get("status") != "passed"
            or saved.get("real_network_opened") is not False
            or saved.get("real_model_called") is not False
            or saved.get("api_key_read_from_environment") is not False
        ):
            raise CrashSafeEvidenceError("saved crash-safe evidence drifted")
    if value.get("status").startswith("frozen_"):
        freeze = value.get("user_freeze", {})
        if (
            freeze.get("status") != "frozen_by_user"
            or freeze.get("frozen_on") != "2026-08-03"
            or freeze.get("per_request_timeout_seconds") != 120
            or freeze.get("batch_internal_timeout_seconds") != 1080
            or freeze.get("recommended_external_process_timeout_seconds")
            != 1200
            or freeze.get("persistence_order_frozen") is not True
            or freeze.get("atomic_event_log_and_state_snapshot_frozen")
            is not True
            or freeze.get("raw_http_must_persist_before_parse") is not True
            or freeze.get("automatic_resume_allowed") is not False
            or freeze.get("new_user_authorization_required_after_recovery")
            is not True
            or freeze.get("freeze_does_not_authorize_real_calls") is not True
            or freeze.get("freeze_does_not_restore_consumed_authorization")
            is not True
            or freeze.get("v2_2_3_remains_paused") is not True
        ):
            raise CrashSafeEvidenceError(
                "frozen crash-safe boundary drifted or grants authority"
            )
        freeze_validation = value.get("freeze_validation", {})
        freeze_evidence_path = PROJECT_ROOT / str(
            freeze_validation.get("evidence_path", "")
        )
        if (
            freeze_validation.get("status") != "passed"
            or freeze_validation.get("termination_recovery_counts")
            != {"reserved": 1, "http_received": 0, "parsed": 0}
            or freeze_validation.get("parse_failure_recovery_counts")
            != {"reserved": 1, "http_received": 1, "parsed": 0}
            or freeze_validation.get("success_recovery_counts")
            != {"reserved": 8, "http_received": 8, "parsed": 8}
            or freeze_validation.get("deadline_stops_before_attempt") is not True
            or freeze_validation.get("evidence_safety_passed") is not True
            or freeze_validation.get("real_network_opened") is not False
            or freeze_validation.get("real_model_called") is not False
            or freeze_validation.get("api_key_read") is not False
            or not freeze_evidence_path.is_file()
        ):
            raise CrashSafeEvidenceError("freeze validation evidence drifted")
        saved_freeze = _read_object(freeze_evidence_path)
        if (
            saved_freeze.get("run_id") != freeze_validation.get("run_id")
            or saved_freeze.get("status") != "passed"
            or saved_freeze.get("automatic_resume_allowed") is not False
            or saved_freeze.get("new_user_authorization_required_after_recovery")
            is not True
            or saved_freeze.get("real_network_opened") is not False
            or saved_freeze.get("real_model_called") is not False
            or saved_freeze.get("api_key_read_from_environment") is not False
        ):
            raise CrashSafeEvidenceError("saved freeze validation evidence drifted")
    return value


class BatchACrashSafeJournal:
    """Append atomic events before maintaining a recoverable state snapshot."""

    def __init__(
        self,
        *,
        output_dir: Path,
        run_id: str,
        secret: str,
        execution_mode: str,
        question_ids: tuple[str, ...],
        model: str,
        response_attempt_upper_bound: int,
        automatic_retry_count: int,
        request_timeout_seconds: float,
        batch_timeout_seconds: float,
    ) -> None:
        self.output_dir = output_dir
        self.run_id = run_id
        self._secret = secret
        self.state_path = output_dir / "run_state.json"
        self.events_dir = output_dir / "events"
        self.http_dir = output_dir / "responses" / "http"
        self.parsed_dir = output_dir / "responses" / "parsed"
        self._event_index = 0
        self._state: dict[str, Any] = {
            "schema_version": "1.5.6-h3-batch-a-crash-safe-run-state-v1",
            "run_id": run_id,
            "status": "initialized",
            "execution_mode": execution_mode,
            "question_ids": list(question_ids),
            "model": model,
            "response_attempt_upper_bound": response_attempt_upper_bound,
            "automatic_retry_count": automatic_retry_count,
            "request_timeout_seconds": request_timeout_seconds,
            "batch_timeout_seconds": batch_timeout_seconds,
            "started_at": _now(),
            "updated_at": _now(),
            "current_question_id": None,
            "attempted": 0,
            "http_responses_received": 0,
            "parsed_responses": 0,
            "failed_attempts": 0,
            "last_event_index": 0,
            "last_event_type": "initialized",
            "event_files": [],
            "http_response_files": [],
            "parsed_response_files": [],
            "completed_question_ids": [],
            "failed_question_id": None,
            "authorization_consumed_when_attempt_reserved": False,
            "automatic_resume_allowed": False,
            "recovery_requires_new_user_authorization": True,
            "api_key_saved": False,
            "authorization_header_value_saved": False,
            "request_headers_saved": False,
            "request_body_saved": False,
            "local_absolute_paths_saved": False,
        }

    @property
    def state(self) -> dict[str, Any]:
        return dict(self._state)

    def initialize(self) -> None:
        if self.state_path.exists():
            raise CrashSafeEvidenceError(
                "refusing to overwrite an existing crash-safe run state"
            )
        self.output_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(
            self.state_path, self._state, secret=self._secret
        )
        self._record("run_initialized", {})

    def _record(self, event_type: str, payload: dict[str, Any]) -> None:
        self._event_index += 1
        event_name = f"event_{self._event_index:04d}.json"
        relative_event = f"events/{event_name}"
        event = {
            "schema_version": "1.5.6-h3-batch-a-crash-safe-event-v1",
            "run_id": self.run_id,
            "event_index": self._event_index,
            "event_type": event_type,
            "occurred_at": _now(),
            "payload": payload,
        }
        _atomic_write_json(
            self.events_dir / event_name,
            event,
            secret=self._secret,
        )
        self._state["updated_at"] = event["occurred_at"]
        self._state["last_event_index"] = self._event_index
        self._state["last_event_type"] = event_type
        self._state["event_files"].append(relative_event)
        _atomic_write_json(
            self.state_path, self._state, secret=self._secret
        )

    def question_started(self, question_id: str) -> None:
        self._state["status"] = "question_running"
        self._state["current_question_id"] = question_id
        self._record("question_started", {"question_id": question_id})

    def question_finished(self, question_id: str, *, passed: bool) -> None:
        if passed:
            self._state["completed_question_ids"].append(question_id)
            self._state["status"] = "question_completed"
        else:
            self._state["failed_question_id"] = question_id
            self._state["status"] = "failed_stopped"
        self._record(
            "question_finished",
            {"question_id": question_id, "passed": passed},
        )

    def batch_finished(self, *, passed: bool) -> None:
        self._state["status"] = (
            "passed_deterministic_pending_manual_review"
            if passed
            else "failed_stopped"
        )
        self._record("batch_finished", {"passed": passed})

    def response_event(self, event_type: str, payload: dict[str, Any]) -> None:
        if event_type == "attempt_reserved":
            attempt_index = int(payload["attempt_index"])
            self._state["attempted"] = max(
                int(self._state["attempted"]), attempt_index
            )
            self._state["authorization_consumed_when_attempt_reserved"] = True
            self._state["status"] = "attempt_reserved_waiting_for_transport"
            self._record(
                event_type,
                {
                    "attempt_index": attempt_index,
                    "question_id": self._state["current_question_id"],
                    "remaining_batch_seconds": payload.get(
                        "remaining_batch_seconds"
                    ),
                    "effective_request_timeout_seconds": payload.get(
                        "effective_request_timeout_seconds"
                    ),
                },
            )
            return
        if event_type == "http_response_received":
            attempt_index = int(payload["attempt_index"])
            filename = f"response_{attempt_index:03d}.json"
            relative = f"responses/http/{filename}"
            raw_record = {
                "schema_version": "1.5.6-h3-batch-a-http-response-v1",
                "run_id": self.run_id,
                "attempt_index": attempt_index,
                "received_at": _now(),
                "status_code": int(payload["status_code"]),
                "content_base64": base64.b64encode(
                    bytes(payload["content"])
                ).decode("ascii"),
                "request_headers_saved": False,
                "request_body_saved": False,
            }
            _atomic_write_json(
                self.http_dir / filename,
                raw_record,
                secret=self._secret,
            )
            self._state["http_responses_received"] = max(
                int(self._state["http_responses_received"]), attempt_index
            )
            self._state["http_response_files"].append(relative)
            self._state["status"] = "http_response_persisted_pending_parse"
            self._record(
                event_type,
                {
                    "attempt_index": attempt_index,
                    "status_code": int(payload["status_code"]),
                    "response_file": relative,
                },
            )
            return
        if event_type == "response_parsed":
            attempt_index = int(payload["attempt_index"])
            filename = f"response_{attempt_index:03d}.json"
            relative = f"responses/parsed/{filename}"
            _atomic_write_json(
                self.parsed_dir / filename,
                {
                    "schema_version": "1.5.6-h3-batch-a-parsed-response-v1",
                    "run_id": self.run_id,
                    "attempt_index": attempt_index,
                    "parsed_at": _now(),
                    "provider_response": payload["raw_response"],
                },
                secret=self._secret,
            )
            self._state["parsed_responses"] = max(
                int(self._state["parsed_responses"]), attempt_index
            )
            self._state["parsed_response_files"].append(relative)
            self._state["status"] = "response_parsed"
            self._record(
                event_type,
                {"attempt_index": attempt_index, "response_file": relative},
            )
            return
        if event_type == "attempt_failed":
            self._state["failed_attempts"] = int(
                self._state["failed_attempts"]
            ) + 1
            self._state["status"] = "attempt_failed_stopped"
            message = str(payload["message"])
            message = re.sub(
                r"[A-Za-z]:[\\/][^\s\"']+",
                "<local-path-redacted>",
                message,
            )
            message = re.sub(r"Bearer\s+\S+", "<authorization-redacted>", message)
            self._record(
                event_type,
                {
                    "attempt_index": int(payload["attempt_index"]),
                    "exception_type": str(payload["exception_type"]),
                    "message": message[:1000],
                },
            )
            return
        if event_type == "batch_deadline_reached":
            self._state["status"] = "batch_deadline_reached_before_attempt"
            self._record(event_type, dict(payload))
            return
        raise CrashSafeEvidenceError(f"unsupported response event: {event_type}")


def recover_batch_a_run_state(output_dir: Path) -> dict[str, Any]:
    """Read persisted state/events without resuming execution."""

    state_path = output_dir / "run_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    event_files = sorted((output_dir / "events").glob("event_*.json"))
    events = [json.loads(path.read_text(encoding="utf-8")) for path in event_files]
    reserved = [
        int(item["payload"]["attempt_index"])
        for item in events
        if item.get("event_type") == "attempt_reserved"
    ]
    received = [
        int(item["payload"]["attempt_index"])
        for item in events
        if item.get("event_type") == "http_response_received"
    ]
    parsed = [
        int(item["payload"]["attempt_index"])
        for item in events
        if item.get("event_type") == "response_parsed"
    ]
    return {
        "schema_version": "1.5.6-h3-batch-a-crash-recovery-audit-v1",
        "run_id": state["run_id"],
        "last_persisted_status": state["status"],
        "current_question_id": state.get("current_question_id"),
        "reserved_attempts": max(reserved, default=0),
        "http_responses_received": len(set(received)),
        "parsed_responses": len(set(parsed)),
        "event_count": len(events),
        "authorization_consumed": bool(reserved),
        "automatic_resume_allowed": False,
        "recovery_requires_new_user_authorization": True,
        "raw_http_response_files": list(state.get("http_response_files", [])),
        "parsed_response_files": list(state.get("parsed_response_files", [])),
    }
