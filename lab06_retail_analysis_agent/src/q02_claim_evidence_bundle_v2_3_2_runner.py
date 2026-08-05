"""Crash-safe, single-use real/offline runner for Q02 with V2.3.2 bundles."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Literal

from src.fixed_question_validation import load_frozen_questions, validate_fixed_question
from src.online_native_tool_candidate_v2_1_revision import NATIVE_REAL_MODEL_CONFIRMATION
from src.online_native_tool_candidate_v2_3_2 import NativeToolOnlineCandidateV2_3_2
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
    / "h3_q02_claim_evidence_bundle_v2_3_2_real_checkpoint.json"
)
DEFAULT_CONSUMPTION_ROOT = PROJECT_ROOT / "results" / "raw" / "authorization_consumption"
MODEL = "deepseek-v4-flash"
QUESTION_ID = "Q02"
RESPONSE_CAP = 2
AUTOMATIC_RETRIES = 0
REQUEST_TIMEOUT_SECONDS = 120.0
EXECUTION_TIMEOUT_SECONDS = 360.0
REAL_CONFIRMATION = "I_AUTHORIZE_Q02_CLAIM_EVIDENCE_V2_3_2_REAL_CALLS"
OFFLINE_CONFIRMATION = "I_AUTHORIZE_Q02_CLAIM_EVIDENCE_V2_3_2_OFFLINE_ONLY"


class Q02ClaimEvidenceV2_3_2RunnerError(ValueError):
    """Raised when the exact Q02 V2.3.2 authority or protocol drifts."""


@dataclass(frozen=True)
class Q02ExecutionAuthorityV2_3_2:
    mode: Literal["offline_injected_transport", "real_transport"]
    authorization_id: str
    model: str = MODEL
    question_id: str = QUESTION_ID
    response_attempt_upper_bound: int = RESPONSE_CAP
    automatic_retry_count: int = AUTOMATIC_RETRIES


@dataclass(frozen=True)
class Q02ExecutionResultV2_3_2:
    passed: bool
    summary: dict[str, Any]
    output_dir: Path


def _load_contract() -> dict[str, Any]:
    value = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Q02ClaimEvidenceV2_3_2RunnerError("Q02 V2.3.2 contract must be an object")
    return value


def _validate_exact(
    *, question_id: str, model: str, approved_model_responses: int, automatic_retries: int
) -> None:
    if question_id != QUESTION_ID:
        raise Q02ClaimEvidenceV2_3_2RunnerError("only Q02 is authorized")
    if model != MODEL:
        raise Q02ClaimEvidenceV2_3_2RunnerError("model must be deepseek-v4-flash")
    if approved_model_responses != RESPONSE_CAP:
        raise Q02ClaimEvidenceV2_3_2RunnerError("response cap must be exactly two")
    if automatic_retries != AUTOMATIC_RETRIES:
        raise Q02ClaimEvidenceV2_3_2RunnerError("automatic retries must be zero")


def _consumption_path(authorization_id: str, consumption_root: Path) -> Path:
    return consumption_root / f"{authorization_id}.json"


def validate_real_execution_request(
    *,
    question_id: str,
    model: str,
    approved_model_responses: int,
    automatic_retries: int,
    confirmation: str,
    consumption_root: Path = DEFAULT_CONSUMPTION_ROOT,
) -> Q02ExecutionAuthorityV2_3_2:
    _validate_exact(
        question_id=question_id,
        model=model,
        approved_model_responses=approved_model_responses,
        automatic_retries=automatic_retries,
    )
    if confirmation != REAL_CONFIRMATION:
        raise Q02ClaimEvidenceV2_3_2RunnerError("exact real confirmation is missing")
    contract = _load_contract()
    scope = contract.get("scope", {})
    authorization = contract.get("authorization", {})
    authorization_id = str(authorization.get("authorization_id", ""))
    if (
        contract.get("status") != "authorized_pending_single_execution"
        or scope.get("uses_v2_3_2_claim_evidence_bundle") is not True
        or scope.get("reuses_prior_authorization") is not False
        or authorization.get("status") != "authorized_pending_single_execution"
        or authorization.get("authorized_by_user_current_turn") is not True
        or authorization.get("model") != MODEL
        or authorization.get("question_ids") != [QUESTION_ID]
        or authorization.get("expected_model_responses") != RESPONSE_CAP
        or authorization.get("response_attempt_upper_bound") != RESPONSE_CAP
        or authorization.get("automatic_retry_count") != AUTOMATIC_RETRIES
        or authorization.get("real_model_calls_allowed") is not True
        or authorization.get("single_execution_only") is not True
        or authorization.get("consumed_when_first_attempt_reserved") is not True
        or authorization.get("prior_authorization_restored") is not False
        or authorization.get("authorizes_batch_b") is not False
        or authorization.get("v2_2_3_resume_authorized") is not False
        or not authorization_id
    ):
        raise Q02ClaimEvidenceV2_3_2RunnerError("no exact unconsumed V2.3.2 authority")
    if _consumption_path(authorization_id, consumption_root).exists():
        raise Q02ClaimEvidenceV2_3_2RunnerError("Q02 V2.3.2 authority is already consumed")
    return Q02ExecutionAuthorityV2_3_2(
        mode="real_transport", authorization_id=authorization_id
    )


def validate_offline_execution_request(*, confirmation: str) -> Q02ExecutionAuthorityV2_3_2:
    if confirmation != OFFLINE_CONFIRMATION:
        raise Q02ClaimEvidenceV2_3_2RunnerError("offline confirmation is missing")
    return Q02ExecutionAuthorityV2_3_2(
        mode="offline_injected_transport", authorization_id="offline-not-a-real-authority"
    )


def consume_real_authority(
    authority: Q02ExecutionAuthorityV2_3_2,
    *,
    consumption_root: Path = DEFAULT_CONSUMPTION_ROOT,
) -> Path:
    if authority.mode != "real_transport":
        raise Q02ClaimEvidenceV2_3_2RunnerError("offline authority cannot be consumed")
    consumption_root.mkdir(parents=True, exist_ok=True)
    target = _consumption_path(authority.authorization_id, consumption_root)
    payload = {
        "schema_version": "1.5.6-h3-real-authorization-consumption-v1",
        "authorization_id": authority.authorization_id,
        "consumed_on": datetime.now().astimezone().isoformat(),
        "model": authority.model,
        "question_ids": [authority.question_id],
        "response_attempt_upper_bound": authority.response_attempt_upper_bound,
        "automatic_retry_count": authority.automatic_retry_count,
        "consumed_when": "first_attempt_reserved_before_transport",
        "prior_authorization_restored": False,
        "api_key_saved": False,
        "authorization_header_value_saved": False,
    }
    try:
        with target.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    except FileExistsError as exc:
        raise Q02ClaimEvidenceV2_3_2RunnerError(
            "Q02 V2.3.2 authority is already consumed"
        ) from exc
    return target


def execute_q02_validation(
    *,
    api_key: str,
    registry: Any,
    transport: Any | None,
    authority: Q02ExecutionAuthorityV2_3_2,
    output_parent: Path,
    run_id: str | None = None,
    consumption_root: Path = DEFAULT_CONSUMPTION_ROOT,
) -> Q02ExecutionResultV2_3_2:
    if authority.mode == "offline_injected_transport" and transport is None:
        raise Q02ClaimEvidenceV2_3_2RunnerError("offline execution requires injected transport")
    if authority.mode == "real_transport" and transport is not None:
        raise Q02ClaimEvidenceV2_3_2RunnerError("real execution cannot inject transport")
    actual_run_id = run_id or datetime.now().astimezone().strftime(
        "q02_claim_evidence_v2_3_2_%Y%m%dT%H%M%S_%f%z"
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
        automatic_retry_count=AUTOMATIC_RETRIES,
        request_timeout_seconds=REQUEST_TIMEOUT_SECONDS,
        batch_timeout_seconds=EXECUTION_TIMEOUT_SECONDS,
    )
    journal.initialize()
    consumed = False

    def event_sink(event_type: str, payload: dict[str, Any]) -> None:
        nonlocal consumed
        if event_type == "attempt_reserved" and authority.mode == "real_transport" and not consumed:
            consume_real_authority(authority, consumption_root=consumption_root)
            consumed = True
        journal.response_event(event_type, payload)

    candidate_args: dict[str, Any] = {
        "api_key": api_key,
        "registry": registry,
        "response_limit": RESPONSE_CAP,
        "model": MODEL,
        "question_count": 1,
        "request_timeout_seconds": REQUEST_TIMEOUT_SECONDS,
        "batch_timeout_seconds": EXECUTION_TIMEOUT_SECONDS,
        "batch_started_monotonic": perf_counter(),
        "response_event_sink": event_sink,
        "terminal_question_ids": (QUESTION_ID,),
    }
    if transport is None:
        candidate_args["real_call_confirmation"] = NATIVE_REAL_MODEL_CONFIRMATION
    else:
        candidate_args["transport"] = transport
    candidate = NativeToolOnlineCandidateV2_3_2(**candidate_args)

    journal.question_started(QUESTION_ID)
    outcome = candidate.run_turn(
        session_id=f"SESSION-{actual_run_id.replace('+', '_')}",
        turn_id="TURN-002",
        question=load_frozen_questions()[QUESTION_ID]["question"],
        result_root=f"results/raw/{actual_run_id}",
    )
    validation = validate_fixed_question(QUESTION_ID, outcome)
    snapshot = candidate.response_limit_snapshot()
    transport_audit = candidate.transport_audit_payload()
    wire = transport_audit["requests"]
    failures: list[str] = []
    if outcome.status != "completed":
        failures.append("unexpected_terminal_status")
    if validation.status != "passed_deterministic_pending_manual_review":
        failures.append("new_harness_deterministic_acceptance_failed")
    if [item.tool_name for item in outcome.tool_calls] != ["rank_products"]:
        failures.append("unexpected_tool_sequence")
    if outcome.report_validation is None or outcome.report_validation.status != "passed":
        failures.append("report_validation_failed")
    report_failed_upstream = (
        getattr(outcome, "rejected_report_evidence", None) is not None
        and outcome.error_stage == "report_validation"
    )
    if not report_failed_upstream and len(outcome.charts) != 1:
        failures.append("q02_chart_count_mismatch")
    if snapshot.attempted != 2 or snapshot.completed != 2 or snapshot.failed != 0:
        failures.append("response_accounting_mismatch")
    if [len(item.visible_tool_names) for item in candidate.last_trace] != [7, 0]:
        failures.append("wire_tool_visibility_mismatch")
    if [item["outbound_tool_count"] for item in wire] != [7, 0]:
        failures.append("terminal_tools_not_removed")
    if transport_audit.get("claim_evidence_bundle_version") != "v2.3.2":
        failures.append("v2_3_2_claim_evidence_bundle_missing")
    if (
        wire[-1].get("terminal_evidence_envelope_added") is not True
        or wire[-1].get("outbound_tool_role_message_count") != 0
        or wire[-1].get("projected_tool_message_count") != 1
    ):
        failures.append("terminal_evidence_projection_mismatch")

    rejected = getattr(outcome, "rejected_report_evidence", None)
    root_failure_codes = (
        [item.code for item in rejected.report_validation.issues]
        if report_failed_upstream
        else failures[:1]
    )
    root_failure_stage = (
        "report_validation"
        if report_failed_upstream
        else (outcome.error_stage or "program_acceptance")
    )
    passed = not failures
    case = {
        "schema_version": "1.5.6-h3-q02-claim-evidence-v2.3.2-case-v1",
        "question_id": QUESTION_ID,
        "program_status": "passed_deterministic_pending_manual_review" if passed else "failed_stopped",
        "program_failures": failures,
        "root_failure_stage": None if passed else root_failure_stage,
        "root_failure_codes": [] if passed else root_failure_codes,
        "chart_acceptance_status": (
            "passed"
            if passed
            else (
                "not_evaluated_due_to_upstream_report_validation_failure"
                if report_failed_upstream
                else "failed"
            )
        ),
        "new_harness_validation": validation.model_dump(mode="json"),
        "native_model_trace": _trace_payload(candidate.last_trace),
        "terminal_transport_audit": transport_audit,
        "usage": _usage(outcome.raw_responses),
        "outcome": _outcome_payload(outcome),
    }
    _write_json(output_dir / "Q02.json", case, secret=api_key)
    journal.question_finished(QUESTION_ID, passed=passed)
    summary = {
        "schema_version": "1.5.6-h3-q02-claim-evidence-v2.3.2-summary-v1",
        "run_id": actual_run_id,
        "execution_mode": authority.mode,
        "model": MODEL,
        "question_ids_executed": [QUESTION_ID],
        "expected_model_responses": RESPONSE_CAP,
        "response_attempt_upper_bound": RESPONSE_CAP,
        "automatic_retry_count": AUTOMATIC_RETRIES,
        "actual_response_attempts": snapshot.attempted,
        "completed_model_responses": snapshot.completed,
        "failed_transport_or_provider_attempts": snapshot.failed,
        "status": "passed_deterministic_pending_manual_review" if passed else "failed_stopped",
        "program_failures": failures,
        "root_failure_stage": None if passed else root_failure_stage,
        "root_failure_codes": [] if passed else root_failure_codes,
        "chart_acceptance_status": (
            "passed"
            if passed
            else (
                "not_evaluated_due_to_upstream_report_validation_failure"
                if report_failed_upstream
                else "failed"
            )
        ),
        "tool_reference_answer_status": validation.tool_reference_answer_status,
        "report_content_acceptance_status": validation.report_content_acceptance_status,
        "claim_evidence_bundle_version": transport_audit.get("claim_evidence_bundle_version"),
        "manual_review_status": "pending" if passed else "not_reached",
        "automatic_retry_performed": False,
        "automatic_resume_allowed": False,
        "authorization_consumed": authority.mode == "real_transport" and journal.state["authorization_consumed_when_attempt_reserved"],
        "prior_authorization_restored": False,
        "batch_b_authorized": False,
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
    return Q02ExecutionResultV2_3_2(passed=passed, summary=summary, output_dir=output_dir)


__all__ = [
    "OFFLINE_CONFIRMATION",
    "REAL_CONFIRMATION",
    "Q02ClaimEvidenceV2_3_2RunnerError",
    "Q02ExecutionAuthorityV2_3_2",
    "consume_real_authority",
    "execute_q02_validation",
    "validate_offline_execution_request",
    "validate_real_execution_request",
]
