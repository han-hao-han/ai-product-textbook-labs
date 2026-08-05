"""Guarded batch-A runner with an injectable offline transport boundary."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Literal

from src.deepseek_client import provider_output_was_truncated
from src.fixed_question_validation import (
    load_frozen_questions,
    validate_fixed_question,
)
from src.native_tool_agent_v2_1_revision import (
    FIXED_TOOL_SEQUENCES,
    FROZEN_TOOL_NAMES,
)
from src.online_native_tool_candidate_v2_1_revision import (
    NATIVE_REAL_MODEL_CONFIRMATION,
    NativeToolOnlineCandidateV2_1Revision,
)
from src.q01_q10_batch_a_crash_safe_evidence import (
    BatchACrashSafeJournal,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = (
    PROJECT_ROOT
    / "config"
    / "h3_q01_q10_new_harness_flash_real_validation_plan.candidate.json"
)
IMPLEMENTATION_PATH = (
    PROJECT_ROOT
    / "config"
    / "h3_q01_q10_batch_a_safe_runner_implementation.json"
)
BATCH_A_QUESTION_IDS = ("Q02", "Q06", "Q08", "Q09", "Q10")
BATCH_A_MODEL = "deepseek-v4-flash"
BATCH_A_RESPONSE_ATTEMPT_CAP = 8
BATCH_A_AUTOMATIC_RETRIES = 0
BATCH_A_REQUEST_TIMEOUT_SECONDS = 120.0
BATCH_A_TOTAL_TIMEOUT_SECONDS = 1080.0
BATCH_A_REAL_CONFIRMATION = "I_AUTHORIZE_Q01_Q10_BATCH_A_FLASH_REAL_CALLS"
BATCH_A_OFFLINE_CONFIRMATION = "I_AUTHORIZE_BATCH_A_OFFLINE_INJECTED_TRANSPORT_ONLY"
EXPECTED_RESPONSE_ATTEMPTS = {
    "Q02": 2,
    "Q06": 3,
    "Q08": 1,
    "Q09": 1,
    "Q10": 1,
}
EXPECTED_OUTCOME_STATUS = {
    "Q02": "completed",
    "Q06": "completed",
    "Q08": "needs_clarification",
    "Q09": "boundary",
    "Q10": "boundary",
}
REPORT_UPSTREAM_NOT_EVALUATED = (
    "not_evaluated_due_to_upstream_report_validation_failure"
)
TERMINAL_TRUNCATION_NOT_EVALUATED = (
    "not_evaluated_due_to_terminal_output_truncation"
)


class BatchASafeRunnerError(ValueError):
    """Raised when execution or frozen runner boundaries drift."""


@dataclass(frozen=True)
class ValidatedBatchAExecutionAuthority:
    mode: Literal["offline_injected_transport", "real_transport"]
    batch_id: Literal["A"]
    question_ids: tuple[str, ...]
    model: str
    response_attempt_upper_bound: int
    automatic_retry_count: int


@dataclass(frozen=True)
class BatchAExecutionResult:
    passed: bool
    summary: dict[str, Any]
    cases: tuple[dict[str, Any], ...]
    output_dir: Path


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise BatchASafeRunnerError(f"JSON object required: {path.name}")
    return value


def load_batch_a_runner_implementation() -> dict[str, Any]:
    return _read_object(IMPLEMENTATION_PATH)


def validate_batch_a_runner_implementation(
    contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    value = contract or load_batch_a_runner_implementation()
    if value.get("status") not in {
        "offline_implementation_pending_validation",
        "offline_implementation_validated_pending_user_checkpoint",
    }:
        raise BatchASafeRunnerError("unexpected runner implementation status")
    plan = _read_object(PLAN_PATH)
    prerequisite = value.get("prerequisite", {})
    if (
        plan.get("status") != prerequisite.get("required_plan_status")
        or prerequisite.get("implementation_authorized_by_user") is not True
        or prerequisite.get("real_model_calls_authorized") is not False
    ):
        raise BatchASafeRunnerError("runner prerequisite or authority drifted")
    scope = value.get("scope", {})
    if (
        scope.get("batch_id") != "A"
        or scope.get("question_ids_in_order") != list(BATCH_A_QUESTION_IDS)
        or scope.get("model") != BATCH_A_MODEL
        or scope.get("response_attempt_upper_bound")
        != BATCH_A_RESPONSE_ATTEMPT_CAP
        or scope.get("automatic_retry_count") != 0
        or scope.get("terminal_json_question_ids")
        != list(BATCH_A_QUESTION_IDS)
        or any(
            scope.get(field) is not False
            for field in (
                "h2_reference_answers_changed",
                "prompt_changed",
                "tool_names_or_argument_schemas_changed",
                "new_harness_acceptance_changed",
                "v2_2_3_resumed",
            )
        )
    ):
        raise BatchASafeRunnerError("batch-A implementation scope drifted")
    gate = value.get("authorization_gate", {})
    if (
        gate.get("real_entry_is_default_denied") is not True
        or gate.get("real_authorization_checked_before_api_key_read") is not True
        or gate.get("exact_batch_model_questions_cap_retry_and_confirmation_required") is not True
        or gate.get("offline_injected_transport_requires_separate_test_authority") is not True
        or gate.get("offline_test_authority_cannot_enable_real_transport") is not True
        or gate.get("freeze_does_not_authorize_real_calls") is not True
        or gate.get("real_model_calls_allowed") is not False
        or gate.get("api_key_may_be_read_during_offline_validation") is not False
    ):
        raise BatchASafeRunnerError("authorization gate drifted")
    counting = value.get("response_counting", {})
    if (
        counting.get("reserve_before_transport") is not True
        or counting.get("attempted_includes_transport_failures") is not True
        or counting.get("completed_counts_provider_responses_only") is not True
        or counting.get("failed_counts_transport_or_provider_exceptions") is not True
        or counting.get("expected_success_attempts_by_question")
        != EXPECTED_RESPONSE_ATTEMPTS
        or counting.get("expected_success_total") != 8
        or counting.get("ninth_attempt_rejected_before_transport") is not True
    ):
        raise BatchASafeRunnerError("response counting boundary drifted")
    failure = value.get("failure_stop", {})
    if (
        failure.get("stop_batch_on_first_transport_failure") is not True
        or failure.get("stop_batch_on_first_provider_or_schema_failure") is not True
        or failure.get("stop_batch_on_first_tool_or_dataflow_failure") is not True
        or failure.get("stop_batch_on_first_new_harness_failure") is not True
        or failure.get("later_questions_marked_not_executed") is not True
        or failure.get("automatic_retry_count") != 0
        or failure.get("automatic_resume_after_network_recovery") is not False
    ):
        raise BatchASafeRunnerError("failure-stop boundary drifted")
    evidence = value.get("evidence", {})
    required = (
        "save_case_after_each_executed_question",
        "save_provider_raw_responses",
        "save_native_trace_tool_results_facts_charts_and_report",
        "save_new_harness_validation",
        "save_attempt_completed_and_failed_counts",
        "save_sanitized_failure_stage_and_message",
        "save_safe_transport_audit_without_header_values_or_body",
        "save_summary_even_when_batch_stops",
    )
    forbidden = (
        "api_key_saved",
        "authorization_header_value_saved",
        "request_body_saved",
        "raw_customer_id_exported",
        "raw_retail_rows_exported",
        "local_absolute_paths_saved",
    )
    if not (
        all(evidence.get(field) is True for field in required)
        and all(evidence.get(field) is False for field in forbidden)
    ):
        raise BatchASafeRunnerError("evidence or privacy boundary drifted")
    if value.get("status") == "offline_implementation_validated_pending_user_checkpoint":
        offline = value.get("offline_validation", {})
        evidence_path = PROJECT_ROOT / str(offline.get("evidence_path", ""))
        if (
            offline.get("status") != "passed"
            or offline.get("authorization_gate_blocked_before_api_key_read") is not True
            or offline.get("success_actual_response_attempts") != 8
            or offline.get("success_completed_model_responses") != 8
            or offline.get("success_question_count") != 5
            or offline.get("success_status") != "passed_deterministic_pending_manual_review"
            or offline.get("network_failure_attempts") != 3
            or offline.get("network_failure_completed_responses") != 2
            or offline.get("network_failure_count") != 1
            or offline.get("network_failure_later_questions_not_executed")
            != ["Q08", "Q09", "Q10"]
            or offline.get("semantic_failure_attempts") != 4
            or offline.get("semantic_failure_completed_responses") != 4
            or offline.get("semantic_failure_later_questions_not_executed")
            != ["Q08", "Q09", "Q10"]
            or offline.get("ninth_attempt_blocked_before_underlying_client") is not True
            or offline.get("evidence_safety_passed") is not True
            or offline.get("real_network_opened") is not False
            or offline.get("real_model_called") is not False
            or offline.get("api_key_read") is not False
            or not evidence_path.is_file()
        ):
            raise BatchASafeRunnerError("offline runner evidence drifted")
        saved = _read_object(evidence_path)
        if (
            saved.get("run_id") != offline.get("run_id")
            or saved.get("status") != "passed"
            or saved.get("real_network_opened") is not False
            or saved.get("real_model_called") is not False
            or saved.get("api_key_read_from_environment") is not False
            or saved.get("real_model_calls_allowed") is not False
        ):
            raise BatchASafeRunnerError("saved offline runner evidence drifted")
    return value


def _validate_exact_request(
    *,
    batch_id: str,
    question_ids: list[str] | tuple[str, ...],
    model: str,
    approved_model_responses: int,
    automatic_retries: int,
) -> None:
    if batch_id != "A":
        raise BatchASafeRunnerError("batch must be exactly A")
    if tuple(question_ids) != BATCH_A_QUESTION_IDS:
        raise BatchASafeRunnerError("question order must match frozen batch A")
    if model != BATCH_A_MODEL:
        raise BatchASafeRunnerError("model must be deepseek-v4-flash")
    if approved_model_responses != BATCH_A_RESPONSE_ATTEMPT_CAP:
        raise BatchASafeRunnerError("response attempt cap must be exactly eight")
    if automatic_retries != 0:
        raise BatchASafeRunnerError("automatic retries must be zero")


def validate_offline_execution_request(
    *,
    batch_id: str = "A",
    question_ids: tuple[str, ...] = BATCH_A_QUESTION_IDS,
    model: str = BATCH_A_MODEL,
    approved_model_responses: int = BATCH_A_RESPONSE_ATTEMPT_CAP,
    automatic_retries: int = 0,
    confirmation: str,
) -> ValidatedBatchAExecutionAuthority:
    validate_batch_a_runner_implementation()
    _validate_exact_request(
        batch_id=batch_id,
        question_ids=question_ids,
        model=model,
        approved_model_responses=approved_model_responses,
        automatic_retries=automatic_retries,
    )
    if confirmation != BATCH_A_OFFLINE_CONFIRMATION:
        raise BatchASafeRunnerError("offline injected-transport confirmation is missing")
    return ValidatedBatchAExecutionAuthority(
        mode="offline_injected_transport",
        batch_id="A",
        question_ids=BATCH_A_QUESTION_IDS,
        model=BATCH_A_MODEL,
        response_attempt_upper_bound=BATCH_A_RESPONSE_ATTEMPT_CAP,
        automatic_retry_count=0,
    )


def validate_real_execution_request(
    *,
    batch_id: str,
    question_ids: list[str] | tuple[str, ...],
    model: str,
    approved_model_responses: int,
    automatic_retries: int,
    confirmation: str,
    plan: dict[str, Any] | None = None,
) -> ValidatedBatchAExecutionAuthority:
    validate_batch_a_runner_implementation()
    _validate_exact_request(
        batch_id=batch_id,
        question_ids=question_ids,
        model=model,
        approved_model_responses=approved_model_responses,
        automatic_retries=automatic_retries,
    )
    if confirmation != BATCH_A_REAL_CONFIRMATION:
        raise BatchASafeRunnerError("exact batch-A real-call confirmation is missing")
    candidate = plan or _read_object(PLAN_PATH)
    authority = candidate.get(
        "batch_a_crash_safe_real_revalidation_authorization", {}
    )
    if (
        authority.get("status") != "authorized_pending_single_execution"
        or authority.get("question_ids") != list(BATCH_A_QUESTION_IDS)
        or authority.get("model") != BATCH_A_MODEL
        or authority.get("response_attempt_upper_bound") != 8
        or authority.get("automatic_retry_count") != 0
        or authority.get("authorization_matches_frozen_plan") is not True
        or authority.get("authorization_matches_frozen_crash_safe_boundary")
        is not True
        or authority.get("per_request_timeout_seconds") != 120
        or authority.get("batch_internal_timeout_seconds") != 1080
        or authority.get("external_process_timeout_seconds") != 1200
        or authority.get("single_execution_only") is not True
        or authority.get("authorizes_batch_b") is not False
        or authority.get("v2_2_3_resume_authorized") is not False
        or authority.get("consumed") is not False
        or authority.get("real_model_calls_allowed") is not True
    ):
        raise BatchASafeRunnerError(
            "frozen batch-A plan has no separate unconsumed real-call authority"
        )
    return ValidatedBatchAExecutionAuthority(
        mode="real_transport",
        batch_id="A",
        question_ids=BATCH_A_QUESTION_IDS,
        model=BATCH_A_MODEL,
        response_attempt_upper_bound=8,
        automatic_retry_count=0,
    )


def _sanitize_error(value: str | None) -> str | None:
    if value is None:
        return None
    sanitized = re.sub(r"[A-Za-z]:[\\/][^\s\"']+", "<local-path-redacted>", value)
    sanitized = re.sub(r"Bearer\s+\S+", "Bearer <redacted>", sanitized)
    return sanitized[:1000]


def _safe_json_text(value: Any, *, secret: str) -> str:
    text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if secret and secret in text:
        raise BatchASafeRunnerError("refusing to save API key material")
    if '"Authorization"' in text or "Bearer " in text:
        raise BatchASafeRunnerError("refusing to save authorization header material")
    if re.search(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]", text):
        raise BatchASafeRunnerError("refusing to save local absolute paths")
    return text


def _write_json(path: Path, value: Any, *, secret: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_safe_json_text(value, secret=secret), encoding="utf-8")


def _outcome_payload(outcome: Any) -> dict[str, Any]:
    rejected = getattr(outcome, "rejected_report_evidence", None)
    return {
        "status": outcome.status,
        "session_id": outcome.session_id,
        "turn_id": outcome.turn_id,
        "original_question": outcome.original_question,
        "model_response_count": outcome.model_response_count,
        "tool_calls": [
            {
                "call_id": call.call_id,
                "provider_call_id": call.provider_call_id,
                "tool_name": call.tool_name,
                "arguments": call.arguments,
                "result_path": call.result_path,
                "result": call.result,
                "facts": [fact.model_dump(mode="json") for fact in call.facts],
            }
            for call in outcome.tool_calls
        ],
        "facts": [fact.model_dump(mode="json") for fact in outcome.facts],
        "request_records": [item.model_dump(mode="json") for item in outcome.request_records],
        "policy_records": [item.model_dump(mode="json") for item in outcome.policy_records],
        "charts": [chart.model_dump(mode="json") for chart in outcome.charts],
        "report_draft": None if outcome.report_draft is None else outcome.report_draft.model_dump(mode="json"),
        "report_markdown": outcome.report_markdown,
        "report_validation": None if outcome.report_validation is None else outcome.report_validation.model_dump(mode="json"),
        "rejected_report_evidence": None
        if rejected is None
        else {
            "failure_stage": rejected.failure_stage,
            "report_draft": rejected.report_draft.model_dump(mode="json"),
            "report_validation": rejected.report_validation.model_dump(mode="json"),
            "chart_requests": [
                item.model_dump(mode="json")
                for item in rejected.chart_requests
            ],
            "request_records": [
                item.model_dump(mode="json")
                for item in rejected.request_records
            ],
            "policy_records": [
                item.model_dump(mode="json")
                for item in rejected.policy_records
            ],
            "publishable": rejected.publishable,
            "charts_materialized": rejected.charts_materialized,
        },
        "clarification": None if outcome.clarification is None else outcome.clarification.model_dump(mode="json"),
        "boundary": None if outcome.boundary is None else outcome.boundary.model_dump(mode="json"),
        "error_stage": outcome.error_stage,
        "error_message": _sanitize_error(outcome.error_message),
        "raw_responses": list(outcome.raw_responses),
    }


def _trace_payload(trace: tuple[Any, ...]) -> list[dict[str, Any]]:
    return [
        {
            **asdict(step),
            "visible_tool_names": list(step.visible_tool_names),
        }
        for step in trace
    ]


def _usage(raw_responses: tuple[dict[str, Any], ...]) -> dict[str, int]:
    totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    count = 0
    for raw in raw_responses:
        usage = raw.get("usage")
        if not isinstance(usage, dict):
            continue
        count += 1
        for name in totals:
            if isinstance(usage.get(name), int) and not isinstance(usage.get(name), bool):
                totals[name] += usage[name]
    return {**totals, "responses_with_usage": count}


def _case_checks(
    *,
    question_id: str,
    outcome: Any,
    validation: Any,
    trace: tuple[Any, ...],
    attempted_delta: int,
    completed_delta: int,
    failed_delta: int,
) -> list[str]:
    failures: list[str] = []
    expected_count = EXPECTED_RESPONSE_ATTEMPTS[question_id]
    terminal_truncation = provider_output_was_truncated(
        outcome.raw_responses
    )
    if outcome.status != EXPECTED_OUTCOME_STATUS[question_id]:
        failures.append(
            "terminal_output_truncated"
            if terminal_truncation
            else "unexpected_terminal_status"
        )
    if validation.status != "passed_deterministic_pending_manual_review":
        failures.append("new_harness_deterministic_acceptance_failed")
    if attempted_delta != expected_count:
        failures.append("unexpected_response_attempt_count")
    if completed_delta != expected_count or failed_delta != 0:
        failures.append("provider_response_count_mismatch")
    if len(trace) != expected_count:
        failures.append("native_trace_count_mismatch")
    if len(outcome.raw_responses) != expected_count:
        failures.append("provider_raw_response_count_mismatch")
    expected_tools = list(FIXED_TOOL_SEQUENCES[question_id])
    if [call.tool_name for call in outcome.tool_calls] != expected_tools:
        failures.append("unexpected_tool_sequence")
    if any(
        len(step.visible_tool_names) != 7
        or set(step.visible_tool_names) != set(FROZEN_TOOL_NAMES)
        for step in trace
    ):
        failures.append("not_all_seven_tools_visible")
    expected_choices = ["auto"] * (expected_count - 1) + ["none"]
    expected_formats = [None] * (expected_count - 1) + [{"type": "json_object"}]
    if [step.requested_tool_choice for step in trace] != expected_choices:
        failures.append("terminal_tool_choice_mismatch")
    if [step.requested_response_format for step in trace] != expected_formats:
        failures.append("terminal_response_format_mismatch")
    response_models = [raw.get("model") for raw in outcome.raw_responses]
    if response_models != [BATCH_A_MODEL] * expected_count:
        failures.append("provider_response_model_mismatch")
    if _usage(outcome.raw_responses)["responses_with_usage"] != expected_count:
        failures.append("provider_usage_count_mismatch")
    report_failed_upstream = (
        getattr(outcome, "rejected_report_evidence", None) is not None
        and outcome.error_stage == "report_validation"
    )
    if (
        not report_failed_upstream
        and not terminal_truncation
        and question_id == "Q02"
        and len(outcome.charts) != 1
    ):
        failures.append("q02_chart_count_mismatch")
    if (
        not report_failed_upstream
        and not terminal_truncation
        and question_id == "Q06"
        and len(outcome.charts) != 2
    ):
        failures.append("q06_chart_count_mismatch")
    return failures


def _case_evaluation_states(
    *, question_id: str, outcome: Any, validation: Any
) -> dict[str, str]:
    if provider_output_was_truncated(outcome.raw_responses):
        return {
            "report_traceability": TERMINAL_TRUNCATION_NOT_EVALUATED,
            "report_completeness": TERMINAL_TRUNCATION_NOT_EVALUATED,
            "chart_acceptance": TERMINAL_TRUNCATION_NOT_EVALUATED,
        }
    rejected = getattr(outcome, "rejected_report_evidence", None)
    if rejected is not None and outcome.error_stage == "report_validation":
        report_traceability = "failed"
        chart_acceptance = (
            REPORT_UPSTREAM_NOT_EVALUATED
            if question_id in {"Q02", "Q06"}
            else "not_applicable"
        )
    else:
        report_traceability = (
            "passed"
            if outcome.report_validation is not None
            and outcome.report_validation.status == "passed"
            else "not_applicable"
        )
        if question_id == "Q02":
            chart_acceptance = (
                "passed" if len(outcome.charts) == 1 else "failed"
            )
        elif question_id == "Q06":
            chart_acceptance = (
                "passed" if len(outcome.charts) == 2 else "failed"
            )
        else:
            chart_acceptance = "not_applicable"
    return {
        "report_traceability": report_traceability,
        "report_completeness": (
            validation.report_content_acceptance_status
        ),
        "chart_acceptance": chart_acceptance,
    }


def _root_cause(
    outcome: Any,
    failures: list[str],
) -> tuple[str, list[str], str, list[str], list[str]]:
    if provider_output_was_truncated(outcome.raw_responses):
        return (
            "model_response",
            ["terminal_output_truncated"],
            "terminal_output_truncated",
            [
                item
                for item in failures
                if item != "terminal_output_truncated"
            ],
            [
                "report_traceability",
                "report_completeness",
                "chart_acceptance",
            ],
        )
    rejected = getattr(outcome, "rejected_report_evidence", None)
    if rejected is not None and outcome.error_stage == "report_validation":
        return (
            "report_validation",
            [item.code for item in rejected.report_validation.issues],
            "report_validation_failed",
            list(failures),
            ["report_completeness", "chart_acceptance"],
        )
    stage = outcome.error_stage or "program_acceptance"
    codes = list(failures[:1])
    return (
        stage,
        codes,
        f"{stage}_failed" if outcome.error_stage else failures[0],
        list(failures),
        [],
    )


def _safe_transport_audit(
    *,
    transport: Any,
    authority: ValidatedBatchAExecutionAuthority,
    run_state: dict[str, Any],
) -> dict[str, Any]:
    payload = (
        dict(transport.audit_payload())
        if hasattr(transport, "audit_payload")
        else {}
    )
    safe_requests = []
    for request in payload.get("requests", []):
        safe = dict(request)
        safe.pop("authorization_header_present", None)
        safe.pop("authorization_scheme", None)
        safe_requests.append(safe)
    return {
        "schema_version": "1.5.6-h3-batch-a-safe-transport-audit-v1",
        "execution_mode": authority.mode,
        "attempted": int(run_state.get("attempted", 0)),
        "http_responses_received": int(
            run_state.get("http_responses_received", 0)
        ),
        "parsed_responses": int(run_state.get("parsed_responses", 0)),
        "failed_attempts": int(run_state.get("failed_attempts", 0)),
        "real_network_opened": (
            authority.mode == "real_transport"
            and int(run_state.get("http_responses_received", 0)) > 0
        ),
        "real_model_response_received": (
            authority.mode == "real_transport"
            and int(run_state.get("parsed_responses", 0)) > 0
        ),
        "request_headers_saved": False,
        "request_body_saved": False,
        "authorization_header_value_saved": False,
        "api_key_value_saved": False,
        "api_key_source_saved": False,
        "requests": safe_requests,
    }


def execute_batch_a_validation(
    *,
    api_key: str,
    registry: Any,
    transport: Any | None,
    authority: ValidatedBatchAExecutionAuthority,
    output_parent: Path,
    run_id: str | None = None,
) -> BatchAExecutionResult:
    if authority.question_ids != BATCH_A_QUESTION_IDS:
        raise BatchASafeRunnerError("execution authority question scope drifted")
    if authority.model != BATCH_A_MODEL or authority.response_attempt_upper_bound != 8:
        raise BatchASafeRunnerError("execution authority model or cap drifted")
    if authority.automatic_retry_count != 0:
        raise BatchASafeRunnerError("execution authority permits retries")
    if authority.mode == "offline_injected_transport" and transport is None:
        raise BatchASafeRunnerError("offline authority requires injected transport")
    if authority.mode == "real_transport" and transport is not None:
        raise BatchASafeRunnerError("real authority cannot use offline transport")

    actual_run_id = run_id or datetime.now().astimezone().strftime(
        "q01_q10_batch_a_flash_%Y%m%dT%H%M%S_%f%z"
    )
    output_dir = output_parent / actual_run_id
    relative_root = f"results/raw/{actual_run_id}"
    batch_started_monotonic = perf_counter()
    journal = BatchACrashSafeJournal(
        output_dir=output_dir,
        run_id=actual_run_id,
        secret=api_key,
        execution_mode=authority.mode,
        question_ids=BATCH_A_QUESTION_IDS,
        model=BATCH_A_MODEL,
        response_attempt_upper_bound=8,
        automatic_retry_count=0,
        request_timeout_seconds=BATCH_A_REQUEST_TIMEOUT_SECONDS,
        batch_timeout_seconds=BATCH_A_TOTAL_TIMEOUT_SECONDS,
    )
    journal.initialize()
    candidate_args: dict[str, Any] = {
        "api_key": api_key,
        "registry": registry,
        "response_limit": 8,
        "model": BATCH_A_MODEL,
        "question_count": len(BATCH_A_QUESTION_IDS),
        "terminal_lock_question_ids": BATCH_A_QUESTION_IDS,
        "terminal_json_question_ids": BATCH_A_QUESTION_IDS,
        "request_timeout_seconds": BATCH_A_REQUEST_TIMEOUT_SECONDS,
        "batch_timeout_seconds": BATCH_A_TOTAL_TIMEOUT_SECONDS,
        "batch_started_monotonic": batch_started_monotonic,
        "response_event_sink": journal.response_event,
    }
    if transport is None:
        candidate_args["real_call_confirmation"] = NATIVE_REAL_MODEL_CONFIRMATION
    else:
        candidate_args["transport"] = transport
    candidate = NativeToolOnlineCandidateV2_1Revision(**candidate_args)

    questions = load_frozen_questions()
    cases: list[dict[str, Any]] = []
    failed_attempts: list[dict[str, Any]] = []
    stop_reason: str | None = None
    primary_stop_stage: str | None = None
    primary_stop_codes: list[str] = []
    acceptance_consequences: list[str] = []
    not_evaluated_checks: list[str] = []
    for question_id in BATCH_A_QUESTION_IDS:
        journal.question_started(question_id)
        before = candidate.response_limit_snapshot()
        started = perf_counter()
        outcome = candidate.run_turn(
            session_id=f"SESSION-{re.sub(r'[^A-Za-z0-9_-]', '_', actual_run_id)}",
            turn_id=f"TURN-{int(question_id[1:]):03d}",
            question=questions[question_id]["question"],
            result_root=relative_root,
        )
        elapsed = round(perf_counter() - started, 6)
        after = candidate.response_limit_snapshot()
        validation = validate_fixed_question(question_id, outcome)
        failures = _case_checks(
            question_id=question_id,
            outcome=outcome,
            validation=validation,
            trace=candidate.last_trace,
            attempted_delta=after.attempted - before.attempted,
            completed_delta=after.completed - before.completed,
            failed_delta=after.failed - before.failed,
        )
        case = {
            "schema_version": "1.5.6-h3-batch-a-safe-runner-case-v1",
            "question_id": question_id,
            "elapsed_seconds": elapsed,
            "program_status": "passed_deterministic_pending_manual_review" if not failures else "failed_stopped",
            "program_failures": failures,
            "attempt_counts": {
                "attempted": after.attempted - before.attempted,
                "completed": after.completed - before.completed,
                "failed": after.failed - before.failed,
            },
            "new_harness_validation": validation.model_dump(mode="json"),
            "evaluation_states": _case_evaluation_states(
                question_id=question_id,
                outcome=outcome,
                validation=validation,
            ),
            "manual_review_status": "pending",
            "native_model_trace": _trace_payload(candidate.last_trace),
            "usage": _usage(outcome.raw_responses),
            "outcome": _outcome_payload(outcome),
        }
        cases.append(case)
        _write_json(output_dir / f"{question_id}.json", case, secret=api_key)
        journal.question_finished(question_id, passed=not failures)
        if failures:
            (
                primary_stop_stage,
                primary_stop_codes,
                stop_reason,
                acceptance_consequences,
                not_evaluated_checks,
            ) = _root_cause(outcome, failures)
            case["primary_stop_stage"] = primary_stop_stage
            case["primary_stop_codes"] = primary_stop_codes
            case["acceptance_consequences"] = acceptance_consequences
            case["not_evaluated_checks"] = not_evaluated_checks
            _write_json(
                output_dir / f"{question_id}.json",
                case,
                secret=api_key,
            )
            failed_attempts.append(
                {
                    "question_id": question_id,
                    "reserved_attempt_index": after.attempted,
                    "failure_stage": primary_stop_stage,
                    "failure_message": _sanitize_error(outcome.error_message) or failures[0],
                    "transport_attempt_failed": after.failed > before.failed,
                    "automatic_retry_performed": False,
                }
            )
            break

    snapshot = candidate.response_limit_snapshot()
    executed_ids = [case["question_id"] for case in cases]
    not_executed = [item for item in BATCH_A_QUESTION_IDS if item not in executed_ids]
    passed = (
        len(cases) == len(BATCH_A_QUESTION_IDS)
        and all(case["program_status"] == "passed_deterministic_pending_manual_review" for case in cases)
        and snapshot.attempted == 8
        and snapshot.completed == 8
        and snapshot.failed == 0
    )
    evidence_files = [f"{item}.json" for item in executed_ids]
    evidence_files.extend(
        [
            "run_state.json",
            "events/",
            "responses/http/",
            "responses/parsed/",
            "failed_attempts.json",
            "transport_audit.json",
            "summary.json",
        ]
    )
    summary = {
        "schema_version": "1.5.6-h3-batch-a-safe-runner-summary-v1",
        "run_id": actual_run_id,
        "execution_mode": authority.mode,
        "batch_id": "A",
        "question_ids_authorized": list(BATCH_A_QUESTION_IDS),
        "question_ids_executed": executed_ids,
        "question_ids_not_executed": not_executed,
        "model": BATCH_A_MODEL,
        "response_attempt_upper_bound": 8,
        "automatic_retry_count": 0,
        "request_timeout_seconds": BATCH_A_REQUEST_TIMEOUT_SECONDS,
        "batch_timeout_seconds": BATCH_A_TOTAL_TIMEOUT_SECONDS,
        "actual_response_attempts": snapshot.attempted,
        "completed_model_responses": snapshot.completed,
        "failed_transport_or_provider_attempts": snapshot.failed,
        "status": "passed_deterministic_pending_manual_review" if passed else "failed_stopped",
        "stop_reason": stop_reason,
        "primary_stop_stage": primary_stop_stage,
        "primary_stop_codes": primary_stop_codes,
        "acceptance_consequences": acceptance_consequences,
        "not_evaluated_checks": not_evaluated_checks,
        "manual_review_status": "pending",
        "automatic_retry_performed": False,
        "automatic_resume_allowed": False,
        "evidence_files": evidence_files,
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
    _write_json(output_dir / "failed_attempts.json", failed_attempts, secret=api_key)
    _write_json(
        output_dir / "transport_audit.json",
        _safe_transport_audit(
            transport=transport,
            authority=authority,
            run_state=journal.state,
        ),
        secret=api_key,
    )
    _write_json(output_dir / "summary.json", summary, secret=api_key)
    journal.batch_finished(passed=passed)
    return BatchAExecutionResult(
        passed=passed,
        summary=summary,
        cases=tuple(cases),
        output_dir=output_dir,
    )
