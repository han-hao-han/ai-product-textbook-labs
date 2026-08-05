"""Deterministic checks for the corrected native-tool real-call plan."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = (
    PROJECT_ROOT
    / "config"
    / "h3_native_tool_real_validation_plan_v2_1_revision.candidate.json"
)
QUESTION_PATH = PROJECT_ROOT / "config" / "h2_validation_questions.json"
OLD_PLAN_PATH = (
    PROJECT_ROOT / "config" / "h3_v2_1_real_validation_plan.candidate.json"
)
MAINLINE_PATH = (
    PROJECT_ROOT
    / "config"
    / "h3_native_tool_agent_v2_1_revision.candidate.json"
)


EXPECTED_QUESTION_IDS = ("Q06", "Q08", "Q09")
EXPECTED_CASES = {
    "Q06": {
        "order": 1,
        "responses": 3,
        "terminal": "completed",
        "tools": ["analyze_time_trend", "rank_products"],
    },
    "Q08": {
        "order": 2,
        "responses": 1,
        "terminal": "needs_clarification",
        "tools": [],
    },
    "Q09": {
        "order": 3,
        "responses": 1,
        "terminal": "boundary",
        "tools": [],
    },
}


class NativeToolRealValidationPlanError(ValueError):
    """Raised when the candidate plan drifts from the native mainline."""


@dataclass(frozen=True)
class NativeToolRealPlanPreflight:
    status: str
    question_ids: tuple[str, ...]
    response_attempt_upper_bound: int
    expected_beta_requests: int
    expected_standard_json_requests: int
    automatic_retry_count: int
    stop_on_first_case_failure: bool
    real_model_calls_allowed: bool
    checks: tuple[str, ...]


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise NativeToolRealValidationPlanError(
            f"{path.name} must contain a JSON object"
        )
    return value


def load_native_tool_real_validation_plan() -> dict[str, Any]:
    return _read(PLAN_PATH)


def validate_native_tool_real_validation_plan(
    plan: dict[str, Any] | None = None,
) -> NativeToolRealPlanPreflight:
    candidate = deepcopy(plan) if plan is not None else _read(PLAN_PATH)
    questions = _read(QUESTION_PATH)
    old_plan = _read(OLD_PLAN_PATH)
    mainline = _read(MAINLINE_PATH)
    checks: list[str] = []

    if candidate.get("status") not in {
        "candidate_offline_preflight_pending_user_freeze_and_separate_authorization",
        "offline_preflight_passed_pending_user_freeze_and_separate_authorization",
        "frozen_by_user_pending_compatible_real_call_authorization",
        "frozen_and_real_call_authorized_pending_guarded_runner_execution",
        "frozen_authorized_guarded_runner_offline_validated_pending_execution",
        "frozen_real_validation_failed_after_one_response_pending_user_decision",
    }:
        raise NativeToolRealValidationPlanError(
            "native real-call plan must remain an unfrozen candidate"
        )
    if old_plan.get("status") != "paused_after_mainline_boundaries_reopened":
        raise NativeToolRealValidationPlanError(
            "historical recipe plan must remain paused"
        )
    if mainline.get("status") not in {
        "offline_transport_validated_pending_user_freeze_and_real_plan_redesign",
        "real_plan_redesigned_offline_preflight_passed_pending_user_freeze",
        "five_response_real_plan_frozen_pending_compatible_call_authorization",
        "five_response_real_plan_frozen_and_call_authorized_pending_execution",
        "five_response_real_runner_offline_validated_pending_execution",
        "real_validation_failed_first_response_invalid_arguments_pending_user_decision",
    }:
        raise NativeToolRealValidationPlanError(
            "native mainline must pass offline transport before plan design"
        )
    checks.append("historical_plan_paused_and_native_transport_passed")

    protocol = candidate.get("model_protocol", {})
    if protocol.get("requested_model") != "deepseek-v4-pro":
        raise NativeToolRealValidationPlanError("requested model must stay frozen")
    if protocol.get("accepted_response_models") != ["deepseek-v4-pro"]:
        raise NativeToolRealValidationPlanError(
            "response model acceptance must be explicit"
        )
    if protocol.get("tool_visibility_per_response") != 7:
        raise NativeToolRealValidationPlanError(
            "every response must see all seven tools"
        )
    if (
        protocol.get("standard_json_gate_allowed") is not False
        or protocol.get("recipe_router_allowed") is not False
    ):
        raise NativeToolRealValidationPlanError(
            "JSON gates and recipe routers are forbidden"
        )
    if protocol.get("tool_choice") != "auto":
        raise NativeToolRealValidationPlanError("tool choice must remain auto")
    checks.append("protocol_is_native_seven_tool_only")

    authorization = candidate.get("authorization", {})
    forbidden_authority = (
        "real_model_calls_allowed_by_this_plan",
        "api_key_may_be_read_during_plan_design",
        "network_may_be_opened_during_plan_design",
    )
    if any(authorization.get(field) is not False for field in forbidden_authority):
        raise NativeToolRealValidationPlanError(
            "plan design cannot authorize calls, key reads, or network"
        )
    if (
        authorization.get("separate_user_freeze_required") is not True
        or authorization.get("separate_user_call_authorization_required")
        is not True
    ):
        raise NativeToolRealValidationPlanError(
            "freeze and call authorization must remain separate"
        )
    if authorization.get("future_authorization_must_name_question_ids") != list(
        EXPECTED_QUESTION_IDS
    ):
        raise NativeToolRealValidationPlanError(
            "future authorization must name the exact questions"
        )
    if (
        authorization.get("future_authorization_must_name_response_attempt_upper_bound")
        != 5
    ):
        raise NativeToolRealValidationPlanError(
            "future authorization must name the five-response cap"
        )
    checks.append("design_has_no_call_authority")

    if questions.get("status") != "frozen_by_user":
        raise NativeToolRealValidationPlanError("H2 questions must remain frozen")
    available = {item["id"] for item in questions.get("questions", [])}
    if not set(EXPECTED_QUESTION_IDS).issubset(available):
        raise NativeToolRealValidationPlanError(
            "selected questions must come from frozen Q01-Q10"
        )
    selected = tuple(
        candidate.get("selection_strategy", {}).get(
            "selected_question_ids_in_order", []
        )
    )
    if selected != EXPECTED_QUESTION_IDS:
        raise NativeToolRealValidationPlanError(
            "representative order must be Q06, Q08, Q09"
        )
    checks.append("representative_questions_are_frozen")

    cases = candidate.get("case_gates")
    if not isinstance(cases, list) or len(cases) != 3:
        raise NativeToolRealValidationPlanError("exactly three case gates required")
    if tuple(case.get("question_id") for case in cases) != EXPECTED_QUESTION_IDS:
        raise NativeToolRealValidationPlanError("case gate order changed")
    expected_total = 0
    for case in cases:
        question_id = case["question_id"]
        expected = EXPECTED_CASES[question_id]
        if case.get("order") != expected["order"]:
            raise NativeToolRealValidationPlanError(f"{question_id} order changed")
        if case.get("expected_response_attempts") != expected["responses"]:
            raise NativeToolRealValidationPlanError(
                f"{question_id} response count changed"
            )
        if case.get("expected_terminal_status") != expected["terminal"]:
            raise NativeToolRealValidationPlanError(
                f"{question_id} terminal status changed"
            )
        if case.get("expected_tool_sequence") != expected["tools"]:
            raise NativeToolRealValidationPlanError(
                f"{question_id} tool sequence changed"
            )
        if not case.get("program_acceptance") or not case.get(
            "manual_acceptance"
        ):
            raise NativeToolRealValidationPlanError(
                f"{question_id} requires program and manual acceptance"
            )
        expected_total += expected["responses"]
    dependency = cases[0].get("required_dependency", {})
    if dependency != {
        "source_tool": "analyze_time_trend",
        "source_metric": "peak_period",
        "dependent_period": "custom",
        "dependent_start_date": "2011-11-01",
        "dependent_end_date": "2011-11-30",
        "top_n": 3,
    }:
        raise NativeToolRealValidationPlanError("Q06 dependency gate changed")
    if cases[1].get("required_clarification_topics") != [
        "time_range",
        "metric",
        "comparison_dimension_or_objects",
    ]:
        raise NativeToolRealValidationPlanError("Q08 clarification gate changed")
    if cases[2].get("required_missing_fields") != ["cost", "profit"]:
        raise NativeToolRealValidationPlanError("Q09 boundary gate changed")
    checks.append("case_gates_cover_dependency_clarification_boundary")

    limits = candidate.get("hard_limits", {})
    if expected_total != 5 or limits.get("response_attempt_upper_bound") != 5:
        raise NativeToolRealValidationPlanError(
            "response cap must equal the 3+1+1 native protocol count"
        )
    if (
        limits.get("reserve_attempt_before_transport") is not True
        or limits.get("automatic_retry_count") != 0
        or limits.get("parallel_requests") is not False
        or limits.get("stop_on_first_case_failure") is not True
    ):
        raise NativeToolRealValidationPlanError(
            "five-response zero-retry serial stop gate changed"
        )
    endpoints = limits.get("expected_endpoint_counts_if_all_pass")
    if endpoints != {"beta_strict_tool": 5, "standard_json": 0, "total": 5}:
        raise NativeToolRealValidationPlanError("endpoint count changed")
    if limits.get("token_budget") is not None:
        raise NativeToolRealValidationPlanError(
            "this experiment records usage without a fixed token budget"
        )
    checks.append("five_beta_requests_zero_retry")

    acceptance = candidate.get("stage_acceptance", {})
    for field in (
        "all_case_gates_must_pass",
        "partial_pass_does_not_pass_stage",
        "fixed_question_validation_required",
        "manual_review_required",
        "user_confirmation_required_after_results",
    ):
        if acceptance.get(field) is not True:
            raise NativeToolRealValidationPlanError(f"missing acceptance: {field}")
    if acceptance.get("h3_may_be_frozen_automatically") is not False:
        raise NativeToolRealValidationPlanError("H3 cannot freeze automatically")
    checks.append("all_cases_and_manual_review_required")

    privacy = candidate.get("privacy_boundary", {})
    for field in (
        "raw_retail_rows_sent",
        "customer_id_values_sent",
        "api_key_saved",
        "authorization_header_saved",
        "local_absolute_paths_saved",
    ):
        if privacy.get(field) is not False:
            raise NativeToolRealValidationPlanError(f"privacy boundary changed: {field}")
    change = candidate.get("change_control", {})
    is_frozen = candidate.get("status") in {
        "frozen_by_user_pending_compatible_real_call_authorization",
        "frozen_and_real_call_authorized_pending_guarded_runner_execution",
        "frozen_authorized_guarded_runner_offline_validated_pending_execution",
        "frozen_real_validation_failed_after_one_response_pending_user_decision",
    }
    is_authorized = candidate.get("status") in {
        "frozen_and_real_call_authorized_pending_guarded_runner_execution",
        "frozen_authorized_guarded_runner_offline_validated_pending_execution",
    }
    is_runner_ready = candidate.get("status") == (
        "frozen_authorized_guarded_runner_offline_validated_pending_execution"
    )
    is_failed_run = candidate.get("status") == (
        "frozen_real_validation_failed_after_one_response_pending_user_decision"
    )
    is_runner_implemented = is_runner_ready or is_failed_run
    expected_freeze_value = True if is_frozen else False
    for field in (
        "question_ids_frozen_before_call",
        "response_attempt_upper_bound_frozen_before_call",
        "acceptance_rules_frozen_before_call",
    ):
        if change.get(field) is not expected_freeze_value:
            raise NativeToolRealValidationPlanError(
                f"freeze state is inconsistent for {field}"
            )
    if (
        change.get("real_call_authorized") is not is_authorized
        or change.get("runner_implemented") is not is_runner_implemented
    ):
        raise NativeToolRealValidationPlanError(
            "freeze cannot authorize calls or claim a runner"
        )
    if is_frozen:
        review = candidate.get("prior_incompatible_authorization_review", {})
        if (
            review.get("received_response_attempt_upper_bound") != 10
            or review.get("frozen_response_attempt_upper_bound") != 5
            or review.get("real_call_authorized") is not False
            or review.get("status")
            != "not_accepted_upper_bound_conflicts_with_frozen_plan"
        ):
            raise NativeToolRealValidationPlanError(
                "incompatible ten-response authorization must remain rejected"
            )
    if is_authorized:
        compatible = candidate.get("compatible_authorization", {})
        if (
            compatible.get("question_ids") != list(EXPECTED_QUESTION_IDS)
            or compatible.get("model") != "deepseek-v4-pro"
            or compatible.get("response_attempt_upper_bound") != 5
            or compatible.get("automatic_retry_count") != 0
            or compatible.get("status") != "authorized_by_user"
            or compatible.get("authorization_matches_frozen_plan") is not True
        ):
            raise NativeToolRealValidationPlanError(
                "compatible authorization does not match the frozen plan"
            )
    if is_runner_implemented:
        runner = candidate.get("guarded_runner", {})
        expected_runner_status = (
            "executed_real_run_and_stopped_on_first_failure"
            if is_failed_run
            else "implemented_and_offline_guard_validated"
        )
        if (
            runner.get("status") != expected_runner_status
            or runner.get("question_ids_must_equal")
            != list(EXPECTED_QUESTION_IDS)
            or runner.get("response_attempt_upper_bound_must_equal") != 5
            or runner.get("automatic_retry_count_must_equal") != 0
            or runner.get("authorization_checked_before_api_key_read") is not True
            or runner.get("real_model_called_during_runner_validation") is not False
        ):
            raise NativeToolRealValidationPlanError(
                "guarded runner is not ready for the authorized execution"
            )
    if is_failed_run:
        compatible = candidate.get("compatible_authorization", {})
        real_run = candidate.get("real_validation", {})
        if (
            compatible.get("status") != "consumed_by_failed_run"
            or compatible.get("actual_response_attempts") != 1
            or compatible.get("unused_attempt_capacity_not_reusable") != 4
            or real_run.get("status") != "failed_stopped_on_first_case"
            or real_run.get("actual_response_attempts") != 1
            or real_run.get("question_ids_executed") != ["Q06"]
            or real_run.get("question_ids_not_executed") != ["Q08", "Q09"]
            or real_run.get("additional_real_call_authorized") is not False
        ):
            raise NativeToolRealValidationPlanError(
                "failed real run must consume authorization and stop remaining cases"
            )
    checks.append("privacy_freeze_authorization_still_pending")

    return NativeToolRealPlanPreflight(
        status="passed",
        question_ids=selected,
        response_attempt_upper_bound=5,
        expected_beta_requests=5,
        expected_standard_json_requests=0,
        automatic_retry_count=0,
        stop_on_first_case_failure=True,
        real_model_calls_allowed=is_authorized,
        checks=tuple(checks),
    )
