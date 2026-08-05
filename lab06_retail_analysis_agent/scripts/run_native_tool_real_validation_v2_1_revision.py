"""Run the user-frozen five-response native-tool real validation."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.fixed_question_validation import (  # noqa: E402
    load_frozen_questions,
    validate_fixed_question,
)
from src.native_tool_agent_v2_1_revision import FROZEN_TOOL_NAMES  # noqa: E402
from src.native_tool_real_validation_plan_v2_1_revision import (  # noqa: E402
    EXPECTED_QUESTION_IDS,
    load_native_tool_real_validation_plan,
    validate_native_tool_real_validation_plan,
)
from src.online_native_tool_candidate_v2_1_revision import (  # noqa: E402
    NATIVE_REAL_MODEL_CONFIRMATION,
    NativeToolOnlineCandidateV2_1Revision,
)
from src.retail_cleaning import build_retail_data_layers  # noqa: E402
from src.retail_tools import RetailToolService  # noqa: E402
from src.tool_registry import RetailToolRegistry  # noqa: E402


WORKBOOK_PATH = PROJECT_ROOT / "data" / "raw" / "Online Retail.xlsx"


def _load_dotenv_value(path: Path, variable: str) -> str | None:
    if not path.exists():
        return None
    pattern = re.compile(rf"^\s*{re.escape(variable)}\s*=\s*(.*?)\s*$")
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if match is None:
            continue
        value = match.group(1).strip()
        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in {"'", '"'}
        ):
            value = value[1:-1]
        return value or None
    return None


def _load_api_key() -> str | None:
    return os.environ.get("LLM_API_KEY") or _load_dotenv_value(
        REPOSITORY_ROOT / ".env", "LLM_API_KEY"
    )


def _safe_json_text(value: Any, *, api_key: str) -> str:
    text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if api_key and api_key in text:
        raise ValueError("refusing to save a payload containing the API key")
    if "Bearer " in text or '"Authorization"' in text:
        raise ValueError("refusing to save authorization material")
    return text


def _write_json(path: Path, value: Any, *, api_key: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_safe_json_text(value, api_key=api_key), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--question-id", action="append", required=True)
    parser.add_argument("--approved-model-responses", type=int, required=True)
    parser.add_argument("--automatic-retries", type=int, required=True)
    parser.add_argument("--confirm-real-model-calls", required=True)
    return parser.parse_args()


def validate_execution_request(args: argparse.Namespace) -> dict[str, Any]:
    plan = load_native_tool_real_validation_plan()
    preflight = validate_native_tool_real_validation_plan(plan)
    if tuple(args.question_id) != EXPECTED_QUESTION_IDS:
        raise ValueError("question order must be exactly Q06, Q08, Q09")
    if args.approved_model_responses != 5:
        raise ValueError("approved model response limit must be exactly five")
    if args.automatic_retries != 0:
        raise ValueError("automatic retries must be zero")
    if args.confirm_real_model_calls != NATIVE_REAL_MODEL_CONFIRMATION:
        raise ValueError("exact native real-call confirmation is missing")
    compatible = plan.get("compatible_authorization", {})
    if (
        plan.get("status")
        != "frozen_authorized_guarded_runner_offline_validated_pending_execution"
        or compatible.get("status") != "authorized_by_user"
        or compatible.get("authorization_matches_frozen_plan") is not True
        or preflight.real_model_calls_allowed is not True
    ):
        raise ValueError("frozen plan has no compatible real-call authority")
    return plan


def _outcome_payload(outcome: Any) -> dict[str, Any]:
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
                "facts": [
                    fact.model_dump(mode="json") for fact in call.facts
                ],
            }
            for call in outcome.tool_calls
        ],
        "facts": [fact.model_dump(mode="json") for fact in outcome.facts],
        "charts": [chart.model_dump(mode="json") for chart in outcome.charts],
        "report_draft": (
            None
            if outcome.report_draft is None
            else outcome.report_draft.model_dump(mode="json")
        ),
        "report_markdown": outcome.report_markdown,
        "report_validation": (
            None
            if outcome.report_validation is None
            else outcome.report_validation.model_dump(mode="json")
        ),
        "clarification": (
            None
            if outcome.clarification is None
            else outcome.clarification.model_dump(mode="json")
        ),
        "boundary": (
            None
            if outcome.boundary is None
            else outcome.boundary.model_dump(mode="json")
        ),
        "error_stage": outcome.error_stage,
        "error_message": outcome.error_message,
        "raw_responses": list(outcome.raw_responses),
    }


def _usage(raw_responses: tuple[dict[str, Any], ...]) -> dict[str, int]:
    totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for response in raw_responses:
        usage = response.get("usage")
        if not isinstance(usage, dict):
            continue
        for key in totals:
            value = usage.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                totals[key] += value
    return totals


def _program_checks(
    *,
    question_id: str,
    outcome: Any,
    validation: Any,
    trace: tuple[Any, ...],
    expected_responses: int,
    accepted_models: set[str],
) -> tuple[bool, list[str]]:
    failures: list[str] = []
    if validation.status != "passed":
        failures.append("fixed_question_validation_failed")
    if outcome.model_response_count != expected_responses:
        failures.append("unexpected_model_response_count")
    if len(trace) != outcome.model_response_count:
        failures.append("native_trace_count_mismatch")
    if any(
        len(step.visible_tool_names) != 7
        or set(step.visible_tool_names) != set(FROZEN_TOOL_NAMES)
        for step in trace
    ):
        failures.append("not_all_seven_tools_visible")
    response_models = {
        str(response.get("model"))
        for response in outcome.raw_responses
        if response.get("model") is not None
    }
    if not response_models or not response_models.issubset(accepted_models):
        failures.append("unexpected_provider_response_model")
    if question_id == "Q06" and outcome.status == "completed":
        if len(outcome.charts) != 2:
            failures.append("q06_requires_two_charts")
        referenced = set(outcome.report_validation.referenced_fact_ids)
        for call_id in ("CALL-001", "CALL-002"):
            if not any(
                fact.call_id == call_id and fact.fact_id in referenced
                for fact in outcome.facts
            ):
                failures.append(f"q06_report_missing_{call_id}_fact")
    return not failures, failures


def main() -> int:
    args = parse_args()
    try:
        plan = validate_execution_request(args)
    except ValueError as exc:
        raise SystemExit(f"authorization gate stopped execution: {exc}") from exc

    api_key = _load_api_key()
    if not api_key:
        raise SystemExit("LLM_API_KEY is missing; no real request was sent")
    if not WORKBOOK_PATH.exists():
        raise SystemExit("Online Retail workbook is missing; no real request was sent")

    frame = pd.read_excel(WORKBOOK_PATH)
    registry = RetailToolRegistry(
        RetailToolService(build_retail_data_layers(frame))
    )
    candidate = NativeToolOnlineCandidateV2_1Revision(
        api_key=api_key,
        registry=registry,
        response_limit=5,
        transport=None,
        real_call_confirmation=NATIVE_REAL_MODEL_CONFIRMATION,
        question_count=3,
    )
    questions = load_frozen_questions()
    case_plan = {item["question_id"]: item for item in plan["case_gates"]}
    accepted_models = set(plan["model_protocol"]["accepted_response_models"])
    run_id = datetime.now().astimezone().strftime(
        "native_tool_real_validation_%Y%m%dT%H%M%S_%f%z"
    )
    relative_root = f"results/raw/{run_id}"
    output_root = PROJECT_ROOT / relative_root
    session_id = f"SESSION-{re.sub(r'[^A-Za-z0-9_-]', '_', run_id)}"
    cases: list[dict[str, Any]] = []
    not_executed: list[str] = []
    stopped = False

    for index, question_id in enumerate(EXPECTED_QUESTION_IDS, start=1):
        if stopped:
            not_executed.append(question_id)
            continue
        started = perf_counter()
        outcome = candidate.run_turn(
            session_id=session_id,
            turn_id=f"TURN-{index:03d}",
            question=questions[question_id]["question"],
            result_root=relative_root,
        )
        elapsed = round(perf_counter() - started, 6)
        validation = validate_fixed_question(question_id, outcome)
        program_passed, failures = _program_checks(
            question_id=question_id,
            outcome=outcome,
            validation=validation,
            trace=candidate.last_trace,
            expected_responses=case_plan[question_id][
                "expected_response_attempts"
            ],
            accepted_models=accepted_models,
        )
        case_payload = {
            "question_id": question_id,
            "elapsed_seconds": elapsed,
            "program_validation_status": (
                "passed" if program_passed else "failed"
            ),
            "program_failures": failures,
            "fixed_question_validation": validation.model_dump(mode="json"),
            "usage": _usage(outcome.raw_responses),
            "response_models": [
                response.get("model") for response in outcome.raw_responses
            ],
            "native_model_trace": [
                {
                    "response_index": step.response_index,
                    "visible_tool_names": list(step.visible_tool_names),
                    "action": step.action,
                    "selected_tool_name": step.selected_tool_name,
                    "selected_arguments": step.selected_arguments,
                    "normalized_arguments": step.normalized_arguments,
                    "tool_result_messages_seen": step.tool_result_messages_seen,
                    "requested_tool_choice": step.requested_tool_choice,
                }
                for step in candidate.last_trace
            ],
            "manual_review_status": "pending",
            "manual_review_items": case_plan[question_id]["manual_acceptance"],
            "outcome": _outcome_payload(outcome),
        }
        _write_json(
            output_root / f"{question_id}.json",
            case_payload,
            api_key=api_key,
        )
        cases.append(case_payload)
        if not program_passed:
            stopped = True

    snapshot = candidate.response_limit_snapshot()
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for case in cases:
        for key in total_usage:
            total_usage[key] += case["usage"][key]
    all_program_passed = (
        len(cases) == 3
        and not not_executed
        and all(case["program_validation_status"] == "passed" for case in cases)
    )
    summary = {
        "schema_version": "1.5.6-h3-native-tool-real-validation-run-v1",
        "run_id": run_id,
        "question_ids_authorized": list(EXPECTED_QUESTION_IDS),
        "model_authorized": "deepseek-v4-pro",
        "response_attempt_upper_bound": 5,
        "automatic_retry_count": 0,
        "actual_model_response_attempts": snapshot.attempted,
        "completed_model_responses": snapshot.completed,
        "failed_transport_attempts": snapshot.failed,
        "program_validation_status": (
            "passed_pending_manual_review"
            if all_program_passed
            else "failed_stopped_before_remaining_cases"
        ),
        "manual_review_status": "pending",
        "cases_executed": [case["question_id"] for case in cases],
        "cases_not_executed": not_executed,
        "total_usage": total_usage,
        "privacy_audit": {
            "api_key_saved": False,
            "authorization_header_saved": False,
            "request_body_saved": False,
            "raw_customer_id_exported": False,
            "local_absolute_paths_saved": False,
        },
    }
    _write_json(output_root / "summary.json", summary, api_key=api_key)
    print(json.dumps({**summary, "output_dir": str(output_root)}, ensure_ascii=False, indent=2))
    return 0 if all_program_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
