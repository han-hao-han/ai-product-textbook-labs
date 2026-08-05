"""Crash-safe Q02 checkpoint runner for the V2.3.4.2 protocol guard."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Literal

from src.fixed_question_validation import load_frozen_questions, validate_fixed_question
from src.online_native_tool_candidate_v2_1_revision import NATIVE_REAL_MODEL_CONFIRMATION
from src.online_native_tool_candidate_v2_3_4_2 import NativeToolOnlineCandidateV2_3_4_2
from src.q01_q10_batch_a_crash_safe_evidence import BatchACrashSafeJournal
from src.q01_q10_batch_a_safe_runner import (
    _outcome_payload,
    _trace_payload,
    _usage,
    _write_json,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = (
    PROJECT_ROOT
    / "config"
    / "h3_q02_internal_call_arithmetic_guard_v2_3_4_2_real_checkpoint.candidate.json"
)
CONSUMPTION_ROOT = PROJECT_ROOT / "results" / "raw" / "authorization_consumption"
MODEL = "deepseek-v4-flash"
QUESTION_ID = "Q02"
RESPONSE_CAP = 3
REQUEST_TIMEOUT_SECONDS = 120.0
EXECUTION_TIMEOUT_SECONDS = 480.0
REAL_CONFIRMATION = "I_AUTHORIZE_Q02_V2_3_4_2_REAL_CALLS"
OFFLINE_CONFIRMATION = "I_AUTHORIZE_Q02_V2_3_4_2_OFFLINE_ONLY"


class Q02ProtocolGuardRunnerError(ValueError):
    pass


@dataclass(frozen=True)
class Q02ProtocolGuardAuthority:
    mode: Literal["offline_injected_transport", "real_transport"]
    authorization_id: str


@dataclass(frozen=True)
class Q02ProtocolGuardResult:
    passed: bool
    summary: dict[str, Any]
    output_dir: Path


def _root_failure(
    *, outcome: Any, failures: list[str]
) -> tuple[str | None, list[str]]:
    if not failures:
        return None, []
    message = outcome.error_message or ""
    if (
        outcome.error_stage == "model_response"
        and "model selected an unsupported tool sequence" in message
    ):
        return "model_response", ["model_selected_unsupported_tool_sequence"]
    return outcome.error_stage or "program_acceptance", failures[:1]


def _contract() -> dict[str, Any]:
    value = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Q02ProtocolGuardRunnerError("checkpoint contract must be an object")
    return value


def validate_offline_execution_request(
    *, confirmation: str
) -> Q02ProtocolGuardAuthority:
    if confirmation != OFFLINE_CONFIRMATION:
        raise Q02ProtocolGuardRunnerError("offline confirmation is missing")
    value = _contract()
    if value.get("status") not in {
        "offline_runner_ready_real_checkpoint_not_authorized",
        "authorized_pending_single_execution",
        "real_execution_failed_stopped_authority_consumed",
    }:
        raise Q02ProtocolGuardRunnerError("V2.3.4.2 checkpoint is not ready")
    return Q02ProtocolGuardAuthority("offline_injected_transport", "offline-not-real")


def validate_real_execution_request(
    *,
    question_id: str,
    model: str,
    approved_model_responses: int,
    automatic_retries: int,
    confirmation: str,
    consumption_root: Path = CONSUMPTION_ROOT,
) -> Q02ProtocolGuardAuthority:
    if (question_id, model, approved_model_responses, automatic_retries) != (
        QUESTION_ID,
        MODEL,
        RESPONSE_CAP,
        0,
    ):
        raise Q02ProtocolGuardRunnerError(
            "real request must be exact Q02/Flash/cap3/retry0"
        )
    if confirmation != REAL_CONFIRMATION:
        raise Q02ProtocolGuardRunnerError("exact real confirmation is missing")
    value = _contract()
    authorization = value.get("authorization", {})
    authorization_id = authorization.get("authorization_id")
    if (
        value.get("status") != "authorized_pending_single_execution"
        or authorization.get("status") != "authorized_pending_single_execution"
        or authorization.get("real_model_calls_allowed") is not True
        or authorization.get("single_execution_only") is not True
        or authorization.get("consumed_when_first_attempt_reserved") is not True
        or authorization.get("prior_authorization_restored") is not False
        or not isinstance(authorization_id, str)
        or not authorization_id
    ):
        raise Q02ProtocolGuardRunnerError(
            "no exact unconsumed V2.3.4.2 real authority"
        )
    if (consumption_root / f"{authorization_id}.json").exists():
        raise Q02ProtocolGuardRunnerError(
            "V2.3.4.2 real authority is already consumed"
        )
    return Q02ProtocolGuardAuthority("real_transport", authorization_id)


def _consume(authority: Q02ProtocolGuardAuthority, root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"{authority.authorization_id}.json"
    payload = {
        "schema_version": "1.5.6-h3-real-authorization-consumption-v1",
        "authorization_id": authority.authorization_id,
        "consumed_on": datetime.now().astimezone().isoformat(),
        "model": MODEL,
        "question_ids": [QUESTION_ID],
        "response_attempt_upper_bound": RESPONSE_CAP,
        "automatic_retry_count": 0,
        "consumed_when": "first_attempt_reserved_before_transport",
        "prior_authorization_restored": False,
        "api_key_saved": False,
    }
    try:
        with target.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    except FileExistsError as exc:
        raise Q02ProtocolGuardRunnerError(
            "V2.3.4.2 real authority is already consumed"
        ) from exc


def execute_q02(
    *,
    api_key: str,
    registry: Any,
    transport: Any | None,
    authority: Q02ProtocolGuardAuthority,
    output_parent: Path,
    run_id: str | None = None,
    consumption_root: Path = CONSUMPTION_ROOT,
) -> Q02ProtocolGuardResult:
    if authority.mode == "offline_injected_transport" and transport is None:
        raise Q02ProtocolGuardRunnerError(
            "offline execution requires injected transport"
        )
    if authority.mode == "real_transport" and transport is not None:
        raise Q02ProtocolGuardRunnerError(
            "real execution cannot inject transport"
        )
    actual_run_id = run_id or datetime.now().astimezone().strftime(
        "q02_protocol_guard_v2_3_4_2_%Y%m%dT%H%M%S_%f%z"
    )
    output_dir = output_parent / actual_run_id
    journal = BatchACrashSafeJournal(
        output_dir=output_dir,
        run_id=actual_run_id,
        secret=api_key,
        execution_mode=authority.mode,
        question_ids=(QUESTION_ID,),
        model=MODEL,
        response_attempt_upper_bound=RESPONSE_CAP,
        automatic_retry_count=0,
        request_timeout_seconds=REQUEST_TIMEOUT_SECONDS,
        batch_timeout_seconds=EXECUTION_TIMEOUT_SECONDS,
    )
    journal.initialize()
    consumed = False

    def sink(event_type: str, payload: dict[str, Any]) -> None:
        nonlocal consumed
        if (
            event_type == "attempt_reserved"
            and authority.mode == "real_transport"
            and not consumed
        ):
            _consume(authority, consumption_root)
            consumed = True
        journal.response_event(event_type, payload)

    args: dict[str, Any] = {
        "api_key": api_key,
        "registry": registry,
        "response_limit": RESPONSE_CAP,
        "model": MODEL,
        "question_count": 1,
        "request_timeout_seconds": REQUEST_TIMEOUT_SECONDS,
        "batch_timeout_seconds": EXECUTION_TIMEOUT_SECONDS,
        "batch_started_monotonic": perf_counter(),
        "response_event_sink": sink,
        "terminal_question_ids": (QUESTION_ID,),
    }
    if transport is None:
        args["real_call_confirmation"] = NATIVE_REAL_MODEL_CONFIRMATION
    else:
        args["transport"] = transport
    candidate = NativeToolOnlineCandidateV2_3_4_2(**args)
    journal.question_started(QUESTION_ID)
    outcome = candidate.run_turn(
        session_id=f"SESSION-{actual_run_id.replace('+', '_')}",
        turn_id="TURN-002",
        question=load_frozen_questions()[QUESTION_ID]["question"],
        result_root=f"results/raw/{actual_run_id}",
    )
    fixed = validate_fixed_question(QUESTION_ID, outcome)
    snapshot = candidate.response_limit_snapshot()
    audit = candidate.transport_audit_payload()
    protocol = list(candidate.terminal_protocol_trace)
    failures: list[str] = []
    if outcome.status != "completed":
        failures.append("unexpected_terminal_status")
    if fixed.status != "passed_deterministic_pending_manual_review":
        failures.append("new_harness_deterministic_acceptance_failed")
    if [item.tool_name for item in outcome.tool_calls] != ["rank_products"]:
        failures.append("unexpected_tool_sequence")
    if outcome.report_validation is None or outcome.report_validation.status != "passed":
        failures.append("report_validation_failed")
    if len(outcome.charts) != 1:
        failures.append("q02_chart_count_mismatch")
    if (snapshot.attempted, snapshot.completed, snapshot.failed) != (3, 3, 0):
        failures.append("response_accounting_mismatch")
    if audit.get("request_phases") != [
        "business_tool_selection",
        "section_purpose_atom_selection",
        "final_report_from_call_isolated_section_purpose_slots",
    ]:
        failures.append("request_phase_sequence_mismatch")
    if not audit.get("model_visibility", {}).get(
        "all_model_visible_internal_call_counts_zero"
    ):
        failures.append("model_visible_internal_call_id")
    if len(protocol) != 1 or protocol[0].get("status") != "passed":
        failures.append("terminal_protocol_mapping_failed")
    elif not (
        protocol[0].get("parsed_model_response")
        and protocol[0].get("mapped_program_response")
    ):
        failures.append("raw_parsed_mapped_evidence_missing")
    passed = not failures
    root_stage, root_codes = _root_failure(
        outcome=outcome, failures=failures
    )
    cascade_failures = [] if passed else list(failures)
    case = {
        "schema_version": "1.5.6-h3-q02-v2.3.4.2-case-v1",
        "question_id": QUESTION_ID,
        "program_status": (
            "passed_deterministic_pending_manual_review"
            if passed
            else "failed_stopped"
        ),
        "program_failures": failures,
        "root_failure_stage": root_stage,
        "root_failure_codes": root_codes,
        "cascade_failures": cascade_failures,
        "not_evaluated_after_root_failure": (
            []
            if passed
            else [
                "tool_execution",
                "fact_generation",
                "section_purpose_selection",
                "terminal_report_mapping",
                "formal_report_validation",
                "chart_construction",
            ]
        ),
        "new_harness_validation": fixed.model_dump(mode="json"),
        "native_model_trace": _trace_payload(candidate.last_trace),
        "atom_selection_trace": [
            item.__dict__ for item in candidate.atom_selection_trace
        ],
        "terminal_protocol_trace": protocol,
        "transport_audit": audit,
        "usage": _usage(outcome.raw_responses),
        "outcome": _outcome_payload(outcome),
    }
    _write_json(output_dir / "Q02.json", case, secret=api_key)
    journal.question_finished(QUESTION_ID, passed=passed)
    summary = {
        "schema_version": "1.5.6-h3-q02-v2.3.4.2-summary-v1",
        "run_id": actual_run_id,
        "execution_mode": authority.mode,
        "model": MODEL,
        "question_ids_executed": [QUESTION_ID],
        "expected_model_responses": RESPONSE_CAP,
        "response_attempt_upper_bound": RESPONSE_CAP,
        "automatic_retry_count": 0,
        "actual_response_attempts": snapshot.attempted,
        "completed_model_responses": snapshot.completed,
        "failed_transport_or_provider_attempts": snapshot.failed,
        "status": (
            "passed_deterministic_pending_manual_review"
            if passed
            else "failed_stopped"
        ),
        "program_failures": failures,
        "root_failure_stage": root_stage,
        "root_failure_codes": root_codes,
        "cascade_failures": cascade_failures,
        "model_visible_internal_call_values": audit.get(
            "model_visibility", {}
        ).get("model_visible_internal_call_values", 0),
        "raw_parsed_mapped_saved_separately": bool(
            len(protocol) == 1
            and protocol[0].get("parsed_model_response")
            and protocol[0].get("mapped_program_response")
        ),
        "automatic_retry_performed": False,
        "automatic_resume_allowed": False,
        "authorization_consumed": authority.mode == "real_transport" and consumed,
        "prior_authorization_restored": False,
        "v2_2_3_resumed": False,
        "privacy_audit": {
            "api_key_saved": False,
            "authorization_header_value_saved": False,
            "request_headers_saved": False,
            "request_body_saved": False,
            "raw_customer_id_exported": False,
            "raw_retail_rows_exported": False,
            "local_absolute_paths_saved": False,
        },
    }
    _write_json(output_dir / "summary.json", summary, secret=api_key)
    journal.batch_finished(passed=passed)
    return Q02ProtocolGuardResult(passed, summary, output_dir)


__all__ = [
    "OFFLINE_CONFIRMATION",
    "REAL_CONFIRMATION",
    "Q02ProtocolGuardAuthority",
    "Q02ProtocolGuardResult",
    "Q02ProtocolGuardRunnerError",
    "execute_q02",
    "validate_offline_execution_request",
    "validate_real_execution_request",
]
