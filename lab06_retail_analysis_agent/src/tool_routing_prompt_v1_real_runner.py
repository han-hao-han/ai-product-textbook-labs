"""Crash-safe Q02-first real validation for tool-routing Prompt v1."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Literal

from src.fixed_question_validation import load_frozen_questions, validate_fixed_question
from src.native_tool_agent_v2_1_revision import FIXED_TOOL_SEQUENCES
from src.online_native_tool_candidate_tool_routing_v1 import (
    NativeToolOnlineCandidateToolRoutingV1,
    TOOL_ROUTING_PROMPT_VERSION,
)
from src.online_native_tool_candidate_v2_1_revision import (
    NATIVE_REAL_MODEL_CONFIRMATION,
)
from src.q01_q10_batch_a_crash_safe_evidence import BatchACrashSafeJournal
from src.q01_q10_batch_a_safe_runner import (
    _outcome_payload,
    _trace_payload,
    _usage,
    _write_json,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = PROJECT_ROOT / "config" / "h3_tool_routing_prompt_v1_real_validation.json"
CONSUMPTION_ROOT = PROJECT_ROOT / "results" / "raw" / "authorization_consumption"
MODEL = "deepseek-v4-flash"
QUESTION_ORDER = ("Q02", "Q01", "Q03", "Q04", "Q05", "Q06", "Q07", "Q08", "Q09", "Q10")
EXPECTED_RESPONSES = {
    "Q01": 3, "Q02": 3, "Q03": 3, "Q04": 3, "Q05": 4,
    "Q06": 4, "Q07": 4, "Q08": 1, "Q09": 1, "Q10": 1,
}
EXPECTED_STATUSES = {
    **{question_id: "completed" for question_id in ("Q01", "Q02", "Q03", "Q04", "Q05", "Q06", "Q07")},
    "Q08": "needs_clarification", "Q09": "boundary", "Q10": "boundary",
}
RESPONSE_CAP = sum(EXPECTED_RESPONSES.values())
REQUEST_TIMEOUT_SECONDS = 120.0
EXECUTION_TIMEOUT_SECONDS = 3600.0
REAL_CONFIRMATION = "I_AUTHORIZE_TOOL_ROUTING_V1_Q01_Q10_REAL_CALLS"
OFFLINE_CONFIRMATION = "I_AUTHORIZE_TOOL_ROUTING_V1_OFFLINE_ONLY"


class ToolRoutingRealRunnerError(ValueError):
    pass


@dataclass(frozen=True)
class ToolRoutingAuthority:
    mode: Literal["offline_injected_transport", "real_transport"]
    authorization_id: str


@dataclass(frozen=True)
class ToolRoutingRunResult:
    passed: bool
    summary: dict[str, Any]
    output_dir: Path


def _contract() -> dict[str, Any]:
    value = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ToolRoutingRealRunnerError("real validation contract must be an object")
    return value


def validate_offline_request(*, confirmation: str) -> ToolRoutingAuthority:
    if confirmation != OFFLINE_CONFIRMATION:
        raise ToolRoutingRealRunnerError("offline confirmation is missing")
    return ToolRoutingAuthority("offline_injected_transport", "offline-not-real")


def validate_real_request(
    *, model: str, response_cap: int, automatic_retries: int,
    confirmation: str, consumption_root: Path = CONSUMPTION_ROOT,
) -> ToolRoutingAuthority:
    if (model, response_cap, automatic_retries) != (MODEL, RESPONSE_CAP, 0):
        raise ToolRoutingRealRunnerError("real request must be exact Flash/cap27/retry0")
    if confirmation != REAL_CONFIRMATION:
        raise ToolRoutingRealRunnerError("exact real confirmation is missing")
    value = _contract()
    authorization = value.get("authorization", {})
    authorization_id = authorization.get("authorization_id")
    if (
        value.get("status") != "authorized_pending_single_execution"
        or authorization.get("status") != "authorized_pending_single_execution"
        or authorization.get("real_model_calls_allowed") is not True
        or authorization.get("single_execution_only") is not True
        or authorization.get("consumed_when_first_attempt_reserved") is not True
        or not isinstance(authorization_id, str)
        or not authorization_id
    ):
        raise ToolRoutingRealRunnerError("no exact unconsumed real authority")
    if (consumption_root / f"{authorization_id}.json").exists():
        raise ToolRoutingRealRunnerError("real authority is already consumed")
    return ToolRoutingAuthority("real_transport", authorization_id)


def _consume(
    authority: ToolRoutingAuthority,
    root: Path,
    *,
    question_order: tuple[str, ...],
    response_cap: int,
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"{authority.authorization_id}.json"
    payload = {
        "schema_version": "1.5.6-h3-real-authorization-consumption-v1",
        "authorization_id": authority.authorization_id,
        "consumed_on": datetime.now().astimezone().isoformat(),
        "model": MODEL,
        "question_ids": list(question_order),
        "response_attempt_upper_bound": response_cap,
        "automatic_retry_count": 0,
        "consumed_when": "first_attempt_reserved_before_transport",
        "api_key_saved": False,
    }
    try:
        with target.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    except FileExistsError as exc:
        raise ToolRoutingRealRunnerError("real authority is already consumed") from exc


def _root_failure(
    outcome: Any, failures: list[str], fixed: Any | None = None
) -> tuple[str | None, list[str]]:
    if not failures:
        return None, []
    message = outcome.error_message or ""
    if outcome.error_stage == "model_response" and "unsupported tool sequence" in message:
        return "model_response", ["model_selected_unsupported_tool_sequence"]
    if outcome.error_stage == "model_response" and "多个工具调用" in message:
        return "model_response", ["model_emitted_multiple_tool_calls"]
    if outcome.error_stage == "terminal_protocol_validation":
        marker = "terminal_protocol_validation: "
        code = message.split(marker, 1)[1].split(":", 1)[0] if marker in message else "terminal_protocol_validation_failed"
        return "terminal_protocol_validation", [code]
    if outcome.error_stage == "report_validation":
        rejected = outcome.rejected_report_evidence or {}
        if isinstance(rejected, dict):
            validation = rejected.get("report_validation", {})
        elif hasattr(rejected, "model_dump"):
            serialized = rejected.model_dump(mode="json")
            validation = serialized.get("report_validation", {})
        else:
            validation = getattr(rejected, "report_validation", {})
        if isinstance(validation, dict):
            issues = validation.get("issues", [])
        else:
            issues = getattr(validation, "issues", ())
        codes = []
        for item in issues:
            code = item.get("code") if isinstance(item, dict) else getattr(item, "code", None)
            if code:
                codes.append(str(code))
        return "report_validation", codes or ["report_validation_failed"]
    if outcome.error_stage == "argument_schema":
        return "argument_schema", ["tool_argument_schema_validation_failed"]
    if outcome.error_stage == "model_response":
        return "model_response", ["model_response_semantic_validation_failed"]
    if fixed is not None and getattr(fixed, "issues", None):
        paths = [str(item.path) for item in fixed.issues]
        return "fixed_question_acceptance", paths
    return outcome.error_stage or "program_acceptance", failures[:1]


def execute_validation(
    *, api_key: str, registry: Any, transport_factory: Any | None,
    authority: ToolRoutingAuthority, output_parent: Path,
    run_id: str | None = None, consumption_root: Path = CONSUMPTION_ROOT,
    candidate_type: Any = NativeToolOnlineCandidateToolRoutingV1,
    prompt_version: str = TOOL_ROUTING_PROMPT_VERSION,
    schema_namespace: str = "tool-routing-prompt-v1",
    question_order: tuple[str, ...] = QUESTION_ORDER,
    continue_after_failure: bool = False,
    response_allowance_by_question: dict[str, int] | None = None,
) -> ToolRoutingRunResult:
    if authority.mode == "offline_injected_transport" and transport_factory is None:
        raise ToolRoutingRealRunnerError("offline execution requires a transport factory")
    if authority.mode == "real_transport" and transport_factory is not None:
        raise ToolRoutingRealRunnerError("real execution cannot inject a transport factory")
    actual_run_id = run_id or datetime.now().astimezone().strftime(
        f"{schema_namespace.replace('-', '_')}_real_%Y%m%dT%H%M%S_%f%z"
    )
    if not question_order or len(question_order) != len(set(question_order)):
        raise ToolRoutingRealRunnerError("question order must be non-empty and unique")
    if any(question_id not in EXPECTED_RESPONSES for question_id in question_order):
        raise ToolRoutingRealRunnerError("question order contains an unknown question")
    allowances = response_allowance_by_question or {}
    if any(
        item not in question_order or not isinstance(value, int) or value < 0
        for item, value in allowances.items()
    ):
        raise ToolRoutingRealRunnerError("invalid response allowance map")
    response_cap = sum(
        EXPECTED_RESPONSES[item] + allowances.get(item, 0)
        for item in question_order
    )
    output_dir = output_parent / actual_run_id
    started = perf_counter()
    journal = BatchACrashSafeJournal(
        output_dir=output_dir, run_id=actual_run_id, secret=api_key,
        execution_mode=authority.mode, question_ids=question_order, model=MODEL,
        response_attempt_upper_bound=response_cap, automatic_retry_count=0,
        request_timeout_seconds=REQUEST_TIMEOUT_SECONDS,
        batch_timeout_seconds=EXECUTION_TIMEOUT_SECONDS,
    )
    journal.initialize()
    consumed = False
    attempt_offset = 0

    def sink(event_type: str, payload: dict[str, Any]) -> None:
        nonlocal consumed
        adjusted = dict(payload)
        if "attempt_index" in adjusted:
            adjusted["attempt_index"] = (
                int(adjusted["attempt_index"]) + attempt_offset
            )
        if event_type == "attempt_reserved" and authority.mode == "real_transport" and not consumed:
            _consume(
                authority,
                consumption_root,
                question_order=question_order,
                response_cap=response_cap,
            )
            consumed = True
        journal.response_event(event_type, adjusted)

    questions = load_frozen_questions()
    executed: list[str] = []
    cases: list[dict[str, Any]] = []
    batch_failures: list[str] = []
    total_attempted = total_completed = total_failed = 0
    for question_id in question_order:
        expected = EXPECTED_RESPONSES[question_id]
        expected_limit = expected + allowances.get(question_id, 0)
        transport = transport_factory(question_id) if transport_factory is not None else None
        args: dict[str, Any] = {
            "api_key": api_key,
            "registry": registry,
            "response_limit": expected_limit,
            "model": MODEL,
            "question_count": 1,
            "request_timeout_seconds": REQUEST_TIMEOUT_SECONDS,
            "batch_timeout_seconds": EXECUTION_TIMEOUT_SECONDS,
            "batch_started_monotonic": started,
            "response_event_sink": sink,
            "terminal_question_ids": (question_id,),
        }
        if transport is None:
            args["real_call_confirmation"] = NATIVE_REAL_MODEL_CONFIRMATION
        else:
            args["transport"] = transport
        candidate = candidate_type(**args)
        journal.question_started(question_id)
        outcome = candidate.run_turn(
            session_id=f"SESSION-{actual_run_id.replace('+', '_')}-{question_id.lower()}",
            turn_id=f"TURN-{int(question_id[1:]):03d}",
            question=questions[question_id]["question"],
            result_root=f"results/raw/{actual_run_id}",
        )
        fixed = validate_fixed_question(question_id, outcome)
        snapshot = candidate.response_limit_snapshot()
        audit = candidate.transport_audit_payload()
        protocol = list(candidate.terminal_protocol_trace)
        failures: list[str] = []
        if outcome.status != EXPECTED_STATUSES[question_id]:
            failures.append("unexpected_terminal_status")
        if fixed.status != "passed_deterministic_pending_manual_review":
            failures.append("new_harness_deterministic_acceptance_failed")
        if [item.tool_name for item in outcome.tool_calls] != list(FIXED_TOOL_SEQUENCES[question_id]):
            failures.append("unexpected_tool_sequence")
        if not (
            expected <= snapshot.attempted <= expected_limit
            and snapshot.completed == snapshot.attempted
            and snapshot.failed == 0
        ):
            failures.append("response_accounting_mismatch")
        visibility = audit.get("model_visibility", {})
        if not visibility.get("all_model_visible_internal_call_counts_zero"):
            failures.append("model_visible_internal_call_id")
        if question_id <= "Q07":
            if outcome.report_validation is None or outcome.report_validation.status != "passed":
                failures.append("report_validation_failed")
            protocol_statuses = [item.get("status") for item in protocol]
            allowed_protocol = (
                bool(protocol_statuses)
                and protocol_statuses[-1] == "passed"
                and all(
                    item in {"repair_requested", "passed"}
                    for item in protocol_statuses
                )
            )
            if not allowed_protocol:
                failures.append("terminal_protocol_mapping_failed")
        elif protocol:
            failures.append("unexpected_terminal_protocol_trace")
        root_stage, root_codes = _root_failure(outcome, failures, fixed)
        passed = not failures
        case = {
            "schema_version": f"1.5.6-h3-{schema_namespace}-real-case-v1",
            "question_id": question_id,
            "program_status": "passed_deterministic_pending_manual_review" if passed else "failed",
            "program_failures": failures,
            "root_failure_stage": root_stage,
            "root_failure_codes": root_codes,
            "new_harness_validation": fixed.model_dump(mode="json"),
            "native_model_trace": _trace_payload(candidate.last_trace),
            "atom_selection_trace": [item.__dict__ for item in candidate.atom_selection_trace],
            "terminal_protocol_trace": protocol,
            "transport_audit": audit,
            "usage": _usage(outcome.raw_responses),
            "semantic_correction_attempts": max(
                0, snapshot.completed - expected
            ),
            "outcome": _outcome_payload(outcome),
        }
        _write_json(output_dir / f"{question_id}.json", case, secret=api_key)
        journal.question_finished(question_id, passed=passed)
        executed.append(question_id)
        cases.append(case)
        total_attempted += snapshot.attempted
        total_completed += snapshot.completed
        total_failed += snapshot.failed
        attempt_offset = total_attempted
        if not passed:
            batch_failures.extend(f"{question_id}:{item}" for item in failures)
            if not continue_after_failure:
                break
    passed = not batch_failures and tuple(executed) == question_order
    failed_cases = [case for case in cases if case["program_failures"]]
    summary_status = (
        "passed_deterministic_pending_manual_review"
        if passed
        else (
            "completed_with_failures"
            if continue_after_failure and tuple(executed) == question_order
            else "failed_stopped"
        )
    )
    summary = {
        "schema_version": f"1.5.6-h3-{schema_namespace}-real-summary-v1",
        "run_id": actual_run_id,
        "execution_mode": authority.mode,
        "model": MODEL,
        "tool_selection_prompt_version": prompt_version,
        "question_ids_planned": list(question_order),
        "question_ids_executed": executed,
        "status": summary_status,
        "batch_failures": batch_failures,
        "actual_response_attempts": total_attempted,
        "completed_model_responses": total_completed,
        "failed_transport_or_provider_attempts": total_failed,
        "response_attempt_upper_bound": response_cap,
        "automatic_retry_count": 0,
        "automatic_retry_performed": False,
        "semantic_correction_attempts": sum(
            case["semantic_correction_attempts"] for case in cases
        ),
        "authorization_consumed": authority.mode == "real_transport" and consumed,
        "failed_question_ids": [case["question_id"] for case in failed_cases],
        "root_failures": [
            {
                "question_id": case["question_id"],
                "stage": case["root_failure_stage"],
                "codes": case["root_failure_codes"],
            }
            for case in failed_cases
        ],
        "continue_after_failure": continue_after_failure,
        "model_visible_internal_call_values": sum(
            case["transport_audit"].get("model_visibility", {}).get("model_visible_internal_call_values", 0)
            for case in cases
        ),
        "real_model_called": authority.mode == "real_transport",
        "v2_2_3_resumed": False,
        "privacy_audit": {
            "api_key_saved": False, "authorization_header_value_saved": False,
            "request_headers_saved": False, "request_body_saved": False,
            "raw_customer_id_exported": False, "raw_retail_rows_exported": False,
            "local_absolute_paths_saved": False,
        },
    }
    _write_json(output_dir / "summary.json", summary, secret=api_key)
    journal.batch_finished(passed=passed)
    return ToolRoutingRunResult(passed, summary, output_dir)


__all__ = [
    "OFFLINE_CONFIRMATION", "REAL_CONFIRMATION", "RESPONSE_CAP",
    "ToolRoutingAuthority", "ToolRoutingRealRunnerError", "ToolRoutingRunResult",
    "execute_validation", "validate_offline_request", "validate_real_request",
]
