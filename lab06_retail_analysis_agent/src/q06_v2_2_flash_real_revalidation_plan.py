"""Validate the V2.2 single-Q06 Flash real revalidation plan."""

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
    / "h3_q06_v2_2_flash_real_revalidation_plan.candidate.json"
)
TERMINAL_CONTRACT_PATH = (
    PROJECT_ROOT
    / "config"
    / "h3_q06_report_terminal_boundary_v2_2.candidate.json"
)


class Q06V2_2FlashRealPlanError(ValueError):
    pass


@dataclass(frozen=True)
class Q06V2_2FlashRealPlanPreflight:
    status: str
    model: str
    response_attempt_upper_bound: int
    automatic_retry_count: int
    tool_choice_sequence: tuple[str, ...]
    real_model_calls_allowed: bool
    checks: tuple[str, ...]


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Q06V2_2FlashRealPlanError(f"{path.name} must be an object")
    return value


def load_q06_v2_2_flash_real_plan() -> dict[str, Any]:
    return _read_object(PLAN_PATH)


def validate_q06_v2_2_flash_real_plan(
    plan: dict[str, Any] | None = None,
) -> Q06V2_2FlashRealPlanPreflight:
    candidate = deepcopy(plan) if plan is not None else load_q06_v2_2_flash_real_plan()
    checks: list[str] = []
    allowed_statuses = {
        "candidate_pending_guarded_runner_offline_validation_and_user_freeze",
        "candidate_guarded_runner_offline_validated_pending_user_freeze",
        "frozen_pending_separate_real_authorization",
        "frozen_guarded_runner_offline_validated_and_real_call_authorized_pending_execution",
        "frozen_real_validation_completed_pending_manual_review",
        "frozen_real_validation_failed_pending_user_decision",
    }
    if candidate.get("status") not in allowed_statuses:
        raise Q06V2_2FlashRealPlanError("unexpected plan status")

    terminal = _read_object(TERMINAL_CONTRACT_PATH)
    prerequisite = candidate.get("prerequisite", {})
    if (
        terminal.get("status")
        != "frozen_by_user_pending_separate_real_authorization"
        or prerequisite.get("required_terminal_boundary_status")
        != terminal.get("status")
        or prerequisite.get("default_model") != "deepseek-v4-flash"
    ):
        raise Q06V2_2FlashRealPlanError("frozen V2.2 prerequisite is missing")
    checks.append("frozen_v2_2_terminal_boundary_is_exact")

    scope = candidate.get("scope", {})
    if (
        scope.get("question_ids") != ["Q06"]
        or scope.get("model") != "deepseek-v4-flash"
        or scope.get("pro_calls_allowed") != 0
        or any(
            scope.get(field) is not False
            for field in (
                "prompt_changed",
                "provider_schema_changed",
                "data_changed",
                "acceptance_rules_changed",
                "seven_tool_whitelist_changed",
                "h2_metrics_changed",
            )
        )
    ):
        raise Q06V2_2FlashRealPlanError("scope drifted")
    checks.append("q06_flash_only_without_frozen_input_changes")

    protocol = candidate.get("request_protocol", {})
    if (
        protocol.get("tool_visibility_each_response") != 7
        or protocol.get("tool_choice_sequence") != ["auto", "auto", "none"]
        or protocol.get("thinking") != {"type": "disabled"}
        or protocol.get("temperature") != 0
        or protocol.get("stream") is not False
        or protocol.get("response_format_added") is not False
    ):
        raise Q06V2_2FlashRealPlanError("request protocol drifted")
    checks.append("auto_auto_none_native_protocol_is_exact")

    limits = candidate.get("hard_limits", {})
    if (
        limits.get("response_attempt_upper_bound") != 3
        or limits.get("reserve_attempt_before_transport") is not True
        or limits.get("automatic_retry_count") != 0
        or limits.get("parallel_requests") is not False
        or limits.get("stop_on_first_failure") is not True
        or limits.get("continue_after_transport_error") is not False
        or limits.get("continue_after_schema_or_semantic_failure") is not False
        or limits.get("unused_attempt_capacity_reusable") is not False
    ):
        raise Q06V2_2FlashRealPlanError("hard limits drifted")
    checks.append("three_responses_zero_retry_failure_stops")

    acceptance = candidate.get("program_acceptance", {})
    if (
        acceptance.get("expected_tool_sequence")
        != ["analyze_time_trend", "rank_products"]
        or acceptance.get("third_response_requires_no_tool_call") is not True
        or acceptance.get("fixed_question_validation_required") is not True
        or acceptance.get("report_validation_required") is not True
        or acceptance.get("report_must_reference_both_calls") is not True
        or acceptance.get("chart_count") != 2
        or acceptance.get("chart_types")
        != ["monthly_line", "top_n_horizontal_bar"]
        or acceptance.get("manual_review_required") is not True
    ):
        raise Q06V2_2FlashRealPlanError("acceptance drifted")
    checks.append("facts_charts_report_and_manual_review_are_required")

    authorization = candidate.get("authorization", {})
    if (
        authorization.get("new_exact_user_authorization_required") is not True
        or authorization.get("prior_flash_comparison_authorization_reusable")
        is not False
        or authorization.get("future_authorization_must_name_question_ids")
        != ["Q06"]
        or authorization.get("future_authorization_must_name_model")
        != "deepseek-v4-flash"
        or authorization.get(
            "future_authorization_must_name_response_attempt_upper_bound"
        )
        != 3
        or authorization.get(
            "future_authorization_must_name_automatic_retry_count"
        )
        != 0
    ):
        raise Q06V2_2FlashRealPlanError("authorization boundary drifted")

    runnable = candidate.get("status") == (
        "frozen_guarded_runner_offline_validated_and_real_call_authorized_pending_execution"
    )
    if candidate.get("status") != (
        "candidate_pending_guarded_runner_offline_validation_and_user_freeze"
    ):
        implementation = candidate.get("implementation", {})
        offline = candidate.get("offline_validation", {})
        if (
            implementation.get("guarded_runner_status")
            != "implemented_and_offline_validated"
            or offline.get("status") != "passed"
            or offline.get("current_gate_blocked_before_api_key_read") is not True
            or offline.get("success_tool_choices")
            != ["auto", "auto", "none"]
            or offline.get("success_tool_sequence")
            != ["analyze_time_trend", "rank_products"]
            or offline.get("success_chart_count") != 2
            or offline.get("success_report_validation_status") != "passed"
            or offline.get("failure_response_attempts") != 1
            or offline.get("failure_tool_calls_executed") != 0
            or offline.get("privacy_evidence_guard_passed") is not True
            or any(
                offline.get(field) is not False
                for field in (
                    "real_network_opened",
                    "api_key_read_from_environment",
                    "real_model_called",
                )
            )
        ):
            raise Q06V2_2FlashRealPlanError(
                "guarded runner offline evidence drifted"
            )
    if runnable:
        implementation = candidate.get("implementation", {})
        if (
            authorization.get("status") != "authorized_by_user"
            or authorization.get("real_model_calls_allowed") is not True
            or authorization.get("authorization_matches_frozen_plan") is not True
            or authorization.get("authorized_question_ids") != ["Q06"]
            or authorization.get("authorized_model") != "deepseek-v4-flash"
            or authorization.get("authorized_response_attempt_upper_bound") != 3
            or authorization.get("authorized_automatic_retry_count") != 0
            or implementation.get("guarded_runner_status")
            != "implemented_and_offline_validated"
        ):
            raise Q06V2_2FlashRealPlanError("authorized runner gate is incomplete")
    else:
        if authorization.get("real_model_calls_allowed") is not False:
            raise Q06V2_2FlashRealPlanError("non-runnable plan cannot allow calls")
    if candidate.get("status") in {
        "frozen_real_validation_completed_pending_manual_review",
        "frozen_real_validation_failed_pending_user_decision",
    }:
        if authorization.get("status") not in {
            "consumed_by_completed_run",
            "consumed_by_failed_run",
        }:
            raise Q06V2_2FlashRealPlanError(
                "completed real run must consume authorization"
            )
        real = candidate.get("real_validation", {})
        if (
            real.get("actual_response_attempts") != 3
            or real.get("automatic_retry_performed") is not False
            or real.get("additional_real_call_authorized") is not False
        ):
            raise Q06V2_2FlashRealPlanError("real validation evidence drifted")
    checks.append("separate_authorization_and_runner_gate_are_consistent")

    return Q06V2_2FlashRealPlanPreflight(
        status="passed",
        model="deepseek-v4-flash",
        response_attempt_upper_bound=3,
        automatic_retry_count=0,
        tool_choice_sequence=("auto", "auto", "none"),
        real_model_calls_allowed=runnable,
        checks=tuple(checks),
    )
