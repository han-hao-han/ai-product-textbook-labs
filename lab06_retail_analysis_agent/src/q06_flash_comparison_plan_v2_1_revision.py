"""Validate the frozen single-Q06 Flash comparison plan."""

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
    / "h3_q06_flash_comparison_plan_v2_1_revision.json"
)


class Q06FlashComparisonPlanError(ValueError):
    pass


@dataclass(frozen=True)
class Q06FlashComparisonPreflight:
    status: str
    model: str
    response_attempt_upper_bound: int
    automatic_retry_count: int
    real_model_calls_allowed: bool
    checks: tuple[str, ...]


def load_q06_flash_comparison_plan() -> dict[str, Any]:
    value = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Q06FlashComparisonPlanError("Flash comparison plan must be an object")
    return value


def validate_q06_flash_comparison_plan(
    plan: dict[str, Any] | None = None,
) -> Q06FlashComparisonPreflight:
    candidate = (
        deepcopy(plan) if plan is not None else load_q06_flash_comparison_plan()
    )
    checks: list[str] = []
    allowed_statuses = {
        "frozen_and_authorized_pending_guarded_runner_offline_validation",
        "frozen_authorized_guarded_runner_offline_validated_pending_execution",
        "frozen_flash_comparison_completed_pending_model_selection",
        "frozen_flash_comparison_failed_pending_model_selection",
    }
    if candidate.get("status") not in allowed_statuses:
        raise Q06FlashComparisonPlanError("unexpected Flash comparison status")

    scope = candidate.get("comparison_scope", {})
    if (
        scope.get("question_ids") != ["Q06"]
        or scope.get("candidate_model") != "deepseek-v4-flash"
        or scope.get("baseline_model") != "deepseek-v4-pro"
        or scope.get("baseline_repeated") is not False
        or any(
            scope.get(field) is not False
            for field in (
                "prompt_changed",
                "provider_schema_changed",
                "data_changed",
                "acceptance_rules_changed",
                "tool_whitelist_changed",
                "h2_metrics_changed",
            )
        )
    ):
        raise Q06FlashComparisonPlanError("comparison scope drifted")
    checks.append("same_q06_inputs_and_acceptance_without_pro_repeat")

    protocol = candidate.get("model_protocol", {})
    if (
        protocol.get("requested_model") != "deepseek-v4-flash"
        or protocol.get("accepted_response_models") != ["deepseek-v4-flash"]
        or protocol.get("tool_visibility_per_response") != 7
        or protocol.get("tool_choice") != "auto"
        or protocol.get("thinking") != {"type": "disabled"}
        or protocol.get("temperature") != 0
        or protocol.get("stream") is not False
        or protocol.get("standard_json_gate_allowed") is not False
        or protocol.get("recipe_router_allowed") is not False
    ):
        raise Q06FlashComparisonPlanError("Flash protocol drifted")
    checks.append("flash_native_protocol_is_exact")

    limits = candidate.get("hard_limits", {})
    if (
        limits.get("response_attempt_upper_bound") != 3
        or limits.get("reserve_attempt_before_transport") is not True
        or limits.get("automatic_retry_count") != 0
        or limits.get("parallel_requests") is not False
        or limits.get("stop_on_first_failure") is not True
        or limits.get("unused_attempt_capacity_reusable") is not False
        or limits.get("pro_response_attempts_allowed") != 0
    ):
        raise Q06FlashComparisonPlanError("Flash response boundary drifted")
    checks.append("three_flash_responses_zero_retry_zero_pro_calls")

    authorization = candidate.get("authorization", {})
    if (
        authorization.get("status")
        not in {
            "authorized_by_user",
            "consumed_by_completed_run",
            "consumed_by_failed_run",
        }
        or
        authorization.get("question_ids") != ["Q06"]
        or authorization.get("model") != "deepseek-v4-flash"
        or authorization.get("response_attempt_upper_bound") != 3
        or authorization.get("automatic_retry_count") != 0
        or authorization.get("authorization_matches_frozen_plan") is not True
        or authorization.get("pro_call_authorized") is not False
    ):
        raise Q06FlashComparisonPlanError("Flash authorization drifted")

    runnable = candidate.get("status") == (
        "frozen_authorized_guarded_runner_offline_validated_pending_execution"
    )
    if runnable:
        implementation = candidate.get("implementation", {})
        if (
            authorization.get("status") != "authorized_by_user"
            or
            implementation.get("guarded_runner_status")
            != "implemented_and_offline_validated"
            or implementation.get("real_model_called_during_offline_validation")
            is not False
        ):
            raise Q06FlashComparisonPlanError("Flash runner is not offline validated")
    if candidate.get("status") in {
        "frozen_flash_comparison_completed_pending_model_selection",
        "frozen_flash_comparison_failed_pending_model_selection",
    }:
        if authorization.get("status") not in {
            "consumed_by_completed_run",
            "consumed_by_failed_run",
        }:
            raise Q06FlashComparisonPlanError("Flash run must consume authorization")
        real_run = candidate.get("real_run", {})
        if (
            real_run.get("actual_flash_response_attempts") != 3
            or real_run.get("automatic_retry_performed") is not False
            or real_run.get("actual_pro_response_attempts") != 0
            or real_run.get("extra_tool_executed") is not False
        ):
            raise Q06FlashComparisonPlanError("Flash run evidence drifted")
        runnable = False
    checks.append("authorization_and_runner_status_are_consistent")
    return Q06FlashComparisonPreflight(
        status="passed",
        model="deepseek-v4-flash",
        response_attempt_upper_bound=3,
        automatic_retry_count=0,
        real_model_calls_allowed=runnable,
        checks=tuple(checks),
    )
