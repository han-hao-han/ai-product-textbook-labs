"""Guarded runner for the frozen single-Q06 real revalidation plan."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.deepseek_provider_schema_adapter_v2_1_revision import (  # noqa: E402
    DEEPSEEK_NONE_SENTINEL,
)
from src.fixed_question_validation import (  # noqa: E402
    load_frozen_questions,
    validate_fixed_question,
)
from src.native_tool_agent_v2_1_revision import FROZEN_TOOL_NAMES  # noqa: E402
from src.online_native_tool_candidate_v2_1_revision import (  # noqa: E402
    NATIVE_REAL_MODEL_CONFIRMATION,
    NativeToolOnlineCandidateV2_1Revision,
)
from src.q06_real_revalidation_plan_v2_1_revision import (  # noqa: E402
    load_q06_real_revalidation_plan,
    validate_q06_real_revalidation_plan,
)
from src.retail_cleaning import build_retail_data_layers  # noqa: E402
from src.retail_tools import RetailToolService  # noqa: E402
from src.tool_registry import RetailToolRegistry  # noqa: E402


Q06_REAL_REVALIDATION_CONFIRMATION = (
    "I_AUTHORIZE_Q06_PROVIDER_SCHEMA_REVALIDATION"
)
WORKBOOK_PATH = PROJECT_ROOT / "data" / "raw" / "Online Retail.xlsx"


@dataclass(frozen=True)
class Q06ExecutionResult:
    passed: bool
    case_payload: dict[str, Any]
    summary: dict[str, Any]
    output_dir: Path


@dataclass(frozen=True)
class ValidatedQ06ExecutionAuthority:
    """Created only after the frozen plan and exact request both validate."""

    plan: dict[str, Any]
    question_id: str
    model: str
    response_attempt_upper_bound: int
    automatic_retry_count: int


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--question-id", required=True)
    parser.add_argument("--approved-model-responses", type=int, required=True)
    parser.add_argument("--automatic-retries", type=int, required=True)
    parser.add_argument("--confirm-real-model-calls", required=True)
    return parser.parse_args()


def validate_execution_request(
    args: argparse.Namespace,
    *,
    plan: dict[str, Any] | None = None,
) -> ValidatedQ06ExecutionAuthority:
    candidate = (
        load_q06_real_revalidation_plan() if plan is None else plan
    )
    preflight = validate_q06_real_revalidation_plan(candidate)
    if args.question_id != "Q06":
        raise ValueError("question must be exactly Q06")
    if args.approved_model_responses != 3:
        raise ValueError("approved model response limit must be exactly three")
    if args.automatic_retries != 0:
        raise ValueError("automatic retries must be zero")
    if args.confirm_real_model_calls != Q06_REAL_REVALIDATION_CONFIRMATION:
        raise ValueError("exact Q06 real-call confirmation is missing")
    compatible = candidate.get("compatible_authorization", {})
    if (
        candidate.get("status")
        != "frozen_guarded_runner_offline_validated_and_real_call_authorized_pending_execution"
        or compatible.get("status") != "authorized_by_user"
        or compatible.get("authorization_matches_frozen_plan") is not True
        or preflight.real_model_calls_allowed is not True
    ):
        raise ValueError("frozen Q06 plan has no separate real-call authority")
    return ValidatedQ06ExecutionAuthority(
        plan=candidate,
        question_id="Q06",
        model="deepseek-v4-pro",
        response_attempt_upper_bound=3,
        automatic_retry_count=0,
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


def _usage(raw_responses: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    responses_with_usage = 0
    for response in raw_responses:
        usage = response.get("usage")
        if not isinstance(usage, dict):
            continue
        responses_with_usage += 1
        for key in totals:
            value = usage.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                totals[key] += value
    return {**totals, "responses_with_usage": responses_with_usage}


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
        "error_stage": outcome.error_stage,
        "error_message": outcome.error_message,
        "raw_responses": list(outcome.raw_responses),
    }


def _trace_payload(trace: tuple[Any, ...]) -> list[dict[str, Any]]:
    return [
        {
            "response_index": step.response_index,
            "visible_tool_names": list(step.visible_tool_names),
            "action": step.action,
            "selected_tool_name": step.selected_tool_name,
            "selected_arguments": step.selected_arguments,
            "normalized_arguments": step.normalized_arguments,
            "tool_result_messages_seen": step.tool_result_messages_seen,
            "requested_tool_choice": step.requested_tool_choice,
            "requested_response_format": step.requested_response_format,
        }
        for step in trace
    ]


def _program_checks(
    *,
    outcome: Any,
    validation: Any,
    trace: tuple[Any, ...],
    accepted_models: set[str],
    required_response_formats: list[dict[str, str] | None] | None = None,
    reject_finish_reason_length: bool = False,
) -> tuple[bool, list[str]]:
    failures: list[str] = []
    if validation.status != "passed":
        failures.append("fixed_question_validation_failed")
    if outcome.status != "completed":
        failures.append("q06_not_completed")
    if outcome.model_response_count != 3:
        failures.append("unexpected_model_response_count")
    if len(trace) != outcome.model_response_count:
        failures.append("native_trace_count_mismatch")
    if any(
        len(step.visible_tool_names) != 7
        or set(step.visible_tool_names) != set(FROZEN_TOOL_NAMES)
        for step in trace
    ):
        failures.append("not_all_seven_tools_visible")
    if [call.tool_name for call in outcome.tool_calls] != [
        "analyze_time_trend",
        "rank_products",
    ]:
        failures.append("unexpected_q06_tool_sequence")

    if len(trace) >= 1:
        expected_provider = {
            "period": "complete_months_only",
            "start_date": DEEPSEEK_NONE_SENTINEL,
            "end_date": DEEPSEEK_NONE_SENTINEL,
            "grain": "month",
            "metric": "sales_amount",
            "exclude_incomplete_periods": True,
        }
        expected_normalized = {
            **expected_provider,
            "start_date": None,
            "end_date": None,
        }
        if trace[0].selected_tool_name != "analyze_time_trend":
            failures.append("q06_first_tool_mismatch")
        if trace[0].selected_arguments != expected_provider:
            failures.append("q06_first_provider_arguments_mismatch")
        if trace[0].normalized_arguments != expected_normalized:
            failures.append("q06_first_normalized_arguments_mismatch")
    if len(trace) >= 2:
        expected_second = {
            "period": "custom",
            "start_date": "2011-11-01",
            "end_date": "2011-11-30",
            "metric": "sales_amount",
            "top_n": 3,
        }
        if (
            trace[1].selected_tool_name != "rank_products"
            or trace[1].selected_arguments != expected_second
            or trace[1].tool_result_messages_seen != 1
        ):
            failures.append("q06_fact_dependent_second_call_mismatch")
    if len(trace) >= 3 and (
        trace[2].action != "control_response"
        or trace[2].tool_result_messages_seen != 2
    ):
        failures.append("q06_final_response_mismatch")
    if len(trace) >= 3 and [
        step.requested_tool_choice for step in trace[:3]
    ] != ["auto", "auto", "none"]:
        failures.append("q06_terminal_tool_choice_mismatch")
    if required_response_formats is not None and [
        step.requested_response_format for step in trace[:3]
    ] != required_response_formats:
        failures.append("q06_terminal_response_format_mismatch")

    response_models = {
        str(response.get("model"))
        for response in outcome.raw_responses
        if response.get("model") is not None
    }
    if not response_models or not response_models.issubset(accepted_models):
        failures.append("unexpected_provider_response_model")
    if len(outcome.raw_responses) != outcome.model_response_count:
        failures.append("provider_raw_response_count_mismatch")
    if reject_finish_reason_length and any(
        response.get("choices", [{}])[0].get("finish_reason") == "length"
        for response in outcome.raw_responses
        if isinstance(response.get("choices"), list)
        and response.get("choices")
        and isinstance(response["choices"][0], dict)
    ):
        failures.append("provider_finish_reason_length")
    if (
        _usage(outcome.raw_responses)["responses_with_usage"]
        != outcome.model_response_count
    ):
        failures.append("provider_usage_count_mismatch")
    if len(outcome.charts) != 2:
        failures.append("q06_requires_two_charts")
    if outcome.report_validation is None:
        failures.append("q06_report_validation_missing")
    else:
        referenced = set(outcome.report_validation.referenced_fact_ids)
        for call_id in ("CALL-001", "CALL-002"):
            if not any(
                fact.call_id == call_id and fact.fact_id in referenced
                for fact in outcome.facts
            ):
                failures.append(f"q06_report_missing_{call_id}_fact")
    return not failures, failures


def execute_q06_validation(
    *,
    api_key: str,
    registry: Any,
    transport: Any | None,
    output_parent: Path,
    run_id: str | None = None,
    authority: ValidatedQ06ExecutionAuthority | None = None,
    model: str = "deepseek-v4-pro",
    required_response_formats: list[dict[str, str] | None] | None = None,
    reject_finish_reason_length: bool = False,
) -> Q06ExecutionResult:
    actual_run_id = run_id or datetime.now().astimezone().strftime(
        "q06_real_revalidation_%Y%m%dT%H%M%S_%f%z"
    )
    output_dir = output_parent / actual_run_id
    relative_root = f"results/raw/{actual_run_id}"
    candidate_arguments: dict[str, Any] = {
        "api_key": api_key,
        "registry": registry,
        "response_limit": 3,
        "question_count": 1,
        "model": model,
    }
    if transport is None:
        if authority is None:
            raise ValueError(
                "real Q06 transport requires validated execution authority"
            )
        if authority.model != model:
            raise ValueError(
                "validated execution authority does not match requested model"
            )
        candidate_arguments.update(
            {
                "transport": None,
                "real_call_confirmation": NATIVE_REAL_MODEL_CONFIRMATION,
            }
        )
    else:
        candidate_arguments["transport"] = transport
    candidate = NativeToolOnlineCandidateV2_1Revision(**candidate_arguments)
    started = perf_counter()
    outcome = candidate.run_turn(
        session_id=f"SESSION-{re.sub(r'[^A-Za-z0-9_-]', '_', actual_run_id)}",
        turn_id="TURN-006",
        question=load_frozen_questions()["Q06"]["question"],
        result_root=relative_root,
    )
    elapsed = round(perf_counter() - started, 6)
    validation = validate_fixed_question("Q06", outcome)
    trace = candidate.last_trace
    passed, failures = _program_checks(
        outcome=outcome,
        validation=validation,
        trace=trace,
        accepted_models={model},
        required_response_formats=required_response_formats,
        reject_finish_reason_length=reject_finish_reason_length,
    )
    snapshot = candidate.response_limit_snapshot()
    case_payload = {
        "schema_version": "1.5.6-h3-q06-real-revalidation-case-v1",
        "question_id": "Q06",
        "elapsed_seconds": elapsed,
        "program_validation_status": "passed" if passed else "failed",
        "program_failures": failures,
        "fixed_question_validation": validation.model_dump(mode="json"),
        "usage": _usage(outcome.raw_responses),
        "response_models": [
            response.get("model") for response in outcome.raw_responses
        ],
        "native_model_trace": _trace_payload(trace),
        "manual_review_status": "pending",
        "manual_review_items": [
            "报告清楚区分峰值月份事实与该月商品排名",
            "有限解释没有把描述性峰值写成因果关系",
            "建议没有声称显著性、利润、预测或自动决策",
        ],
        "outcome": _outcome_payload(outcome),
    }
    summary = {
        "schema_version": "1.5.6-h3-q06-real-revalidation-run-v1",
        "run_id": actual_run_id,
        "question_ids_authorized": ["Q06"],
        "model_authorized": model,
        "response_attempt_upper_bound": 3,
        "automatic_retry_count": 0,
        "actual_model_response_attempts": snapshot.attempted,
        "completed_model_responses": snapshot.completed,
        "failed_transport_attempts": snapshot.failed,
        "program_validation_status": (
            "passed_pending_manual_review" if passed else "failed_stopped"
        ),
        "manual_review_status": "pending",
        "usage": case_payload["usage"],
        "evidence_files": ["Q06.json", "summary.json"],
        "privacy_audit": {
            "api_key_saved": False,
            "authorization_header_saved": False,
            "request_body_saved": False,
            "raw_customer_id_exported": False,
            "local_absolute_paths_saved": False,
        },
    }
    _write_json(output_dir / "Q06.json", case_payload, api_key=api_key)
    _write_json(output_dir / "summary.json", summary, api_key=api_key)
    return Q06ExecutionResult(
        passed=passed,
        case_payload=case_payload,
        summary=summary,
        output_dir=output_dir,
    )


def main() -> int:
    args = parse_args()
    try:
        authority = validate_execution_request(args)
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
    result = execute_q06_validation(
        api_key=api_key,
        registry=registry,
        transport=None,
        output_parent=PROJECT_ROOT / "results" / "raw",
        authority=authority,
    )
    print(
        json.dumps(
            {**result.summary, "output_dir": str(result.output_dir)},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
