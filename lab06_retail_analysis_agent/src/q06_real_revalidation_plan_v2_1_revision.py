"""Deterministic validation for the single-Q06 real revalidation plan."""

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
    / "h3_q06_real_revalidation_plan_v2_1_revision.candidate.json"
)
ADAPTER_CONTRACT_PATH = (
    PROJECT_ROOT
    / "config"
    / "h3_deepseek_provider_schema_adapter_v2_1_revision.json"
)
QUESTIONS_PATH = PROJECT_ROOT / "config" / "h2_validation_questions.json"


class Q06RealRevalidationPlanError(ValueError):
    """Raised when the single-question plan broadens or weakens."""


@dataclass(frozen=True)
class Q06RealRevalidationPreflight:
    status: str
    question_ids: tuple[str, ...]
    model: str
    response_attempt_upper_bound: int
    expected_beta_requests: int
    automatic_retry_count: int
    real_model_calls_allowed: bool
    checks: tuple[str, ...]


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Q06RealRevalidationPlanError(
            f"{path.name} must contain a JSON object"
        )
    return value


def load_q06_real_revalidation_plan() -> dict[str, Any]:
    return _read(PLAN_PATH)


def validate_q06_real_revalidation_plan(
    plan: dict[str, Any] | None = None,
) -> Q06RealRevalidationPreflight:
    candidate = deepcopy(plan) if plan is not None else _read(PLAN_PATH)
    adapter = _read(ADAPTER_CONTRACT_PATH)
    questions = _read(QUESTIONS_PATH)
    checks: list[str] = []

    if candidate.get("status") not in {
        "candidate_pending_offline_preflight_user_freeze_and_separate_authorization",
        "offline_preflight_passed_pending_user_freeze_and_separate_authorization",
        "frozen_by_user_pending_guarded_runner_implementation_and_separate_authorization",
        "frozen_guarded_runner_offline_validated_pending_separate_authorization",
        "frozen_guarded_runner_offline_validated_and_real_call_authorized_pending_execution",
        "frozen_real_revalidation_failed_after_three_responses_extra_tool_call_pending_user_decision",
    }:
        raise Q06RealRevalidationPlanError(
            "Q06 revalidation plan must remain an unfrozen candidate"
        )
    if adapter.get("status") != "frozen_by_user":
        raise Q06RealRevalidationPlanError(
            "provider schema adapter must remain frozen"
        )
    frozen_question_ids = {
        item.get("id")
        for item in questions.get("questions", [])
        if isinstance(item, dict)
    }
    if (
        questions.get("status") != "frozen_by_user"
        or "Q06" not in frozen_question_ids
    ):
        raise Q06RealRevalidationPlanError("Q06 must remain frozen")
    checks.append("frozen_adapter_and_q06_retained")

    protocol = candidate.get("model_protocol", {})
    if (
        protocol.get("requested_model") != "deepseek-v4-pro"
        or protocol.get("accepted_response_models") != ["deepseek-v4-pro"]
        or protocol.get("tool_visibility_per_response") != 7
        or protocol.get("tool_choice") != "auto"
        or protocol.get("thinking") != {"type": "disabled"}
        or protocol.get("temperature") != 0
        or protocol.get("stream") is not False
        or protocol.get("standard_json_gate_allowed") is not False
        or protocol.get("recipe_router_allowed") is not False
    ):
        raise Q06RealRevalidationPlanError(
            "model protocol must remain the frozen native seven-tool protocol"
        )
    checks.append("native_deepseek_protocol_is_exact")

    case = candidate.get("case_gate", {})
    if (
        case.get("question_ids") != ["Q06"]
        or case.get("expected_terminal_status") != "completed"
        or case.get("expected_response_attempts") != 3
        or case.get("expected_tool_sequence")
        != ["analyze_time_trend", "rank_products"]
    ):
        raise Q06RealRevalidationPlanError(
            "case must remain the single three-response Q06 chain"
        )
    response_gates = case.get("response_gates", [])
    if len(response_gates) != 3:
        raise Q06RealRevalidationPlanError("Q06 requires exactly three gates")
    first_provider = response_gates[0].get("required_provider_arguments", {})
    first_normalized = response_gates[0].get(
        "required_normalized_arguments", {}
    )
    if (
        first_provider.get("start_date") != "__NONE__"
        or first_provider.get("end_date") != "__NONE__"
        or first_provider.get("grain") != "month"
        or first_normalized.get("start_date") is not None
        or first_normalized.get("end_date") is not None
        or first_normalized.get("grain") != "month"
    ):
        raise Q06RealRevalidationPlanError(
            "first gate must distinguish provider and normalized arguments"
        )
    second = response_gates[1]
    if second.get("required_provider_arguments") != {
        "period": "custom",
        "start_date": "2011-11-01",
        "end_date": "2011-11-30",
        "metric": "sales_amount",
        "top_n": 3,
    }:
        raise Q06RealRevalidationPlanError(
            "second gate must use the frozen peak-month dependency"
        )
    if (
        response_gates[2].get("expected_action") != "control_response"
        or response_gates[2].get("required_tool_result_messages_seen") != 2
    ):
        raise Q06RealRevalidationPlanError(
            "third gate must finalize after both tool results"
        )
    checks.append("provider_normalization_fact_dependency_and_report_are_gated")

    limits = candidate.get("hard_limits", {})
    if (
        limits.get("response_attempt_upper_bound") != 3
        or limits.get("reserve_attempt_before_transport") is not True
        or limits.get("automatic_retry_count") != 0
        or limits.get("parallel_requests") is not False
        or limits.get("stop_on_first_failure") is not True
        or limits.get("unused_attempt_capacity_reusable") is not False
        or limits.get("expected_endpoint_counts_if_pass")
        != {"beta_strict_tool": 3, "standard_json": 0, "total": 3}
    ):
        raise Q06RealRevalidationPlanError(
            "three-response zero-retry stop boundary cannot change"
        )
    checks.append("three_response_limit_and_zero_retry_are_exact")

    authorization = candidate.get("authorization", {})
    if (
        authorization.get("real_model_calls_allowed_by_this_plan") is not False
        or authorization.get("api_key_may_be_read_during_design_or_preflight")
        is not False
        or authorization.get("network_may_be_opened_during_design_or_preflight")
        is not False
        or authorization.get("separate_user_freeze_required") is not True
        or authorization.get("separate_user_call_authorization_required")
        is not True
        or authorization.get("future_authorization_must_name_question_ids")
        != ["Q06"]
        or authorization.get(
            "future_authorization_must_name_response_attempt_upper_bound"
        )
        != 3
        or authorization.get("future_authorization_must_name_automatic_retry_count")
        != 0
        or authorization.get("prior_five_response_authorization_reusable")
        is not False
    ):
        raise Q06RealRevalidationPlanError(
            "design must not grant or inherit real-call authority"
        )
    acceptance = candidate.get("stage_acceptance", {})
    if (
        acceptance.get("manual_review_required") is not True
        or acceptance.get("h3_may_be_frozen_automatically") is not False
        or acceptance.get(
            "normalized_arguments_alone_do_not_pass_provider_adapter_gate"
        )
        is not True
    ):
        raise Q06RealRevalidationPlanError(
            "manual and provider-argument acceptance cannot be weakened"
        )
    checks.append("no_authority_and_manual_review_retained")

    is_frozen = candidate.get("status") in {
        "frozen_by_user_pending_guarded_runner_implementation_and_separate_authorization",
        "frozen_guarded_runner_offline_validated_pending_separate_authorization",
        "frozen_guarded_runner_offline_validated_and_real_call_authorized_pending_execution",
        "frozen_real_revalidation_failed_after_three_responses_extra_tool_call_pending_user_decision",
    }
    if is_frozen:
        freeze = candidate.get("user_freeze", {})
        if (
            freeze.get("status") != "frozen_by_user"
            or freeze.get("question_ids") != ["Q06"]
            or freeze.get("model") != "deepseek-v4-pro"
            or freeze.get("response_attempt_upper_bound") != 3
            or freeze.get("automatic_retry_count") != 0
            or freeze.get("freeze_does_not_authorize_real_calls") is not True
            or freeze.get("prior_five_response_authorization_reusable")
            is not False
        ):
            raise Q06RealRevalidationPlanError(
                "user freeze must preserve Q06, model, cap, zero retry, and no authority"
            )
        checks.append("user_freeze_matches_exact_plan_without_call_authority")

    runner_ready = candidate.get("status") in {
        "frozen_guarded_runner_offline_validated_pending_separate_authorization",
        "frozen_guarded_runner_offline_validated_and_real_call_authorized_pending_execution",
        "frozen_real_revalidation_failed_after_three_responses_extra_tool_call_pending_user_decision",
    }
    if runner_ready:
        implementation = candidate.get("implementation_boundary", {})
        if (
            implementation.get("guarded_runner_status")
            != "implemented_and_offline_guard_validated"
            or implementation.get("guarded_runner")
            != "scripts/run_q06_real_revalidation_v2_1_revision.py"
            or implementation.get("guarded_runner_test")
            != "tests/test_q06_real_revalidation_runner_v2_1_revision.py"
            or implementation.get("authorization_checked_before_api_key_read")
            is not True
            or implementation.get(
                "real_transport_requires_validated_execution_authority"
            )
            is not True
            or implementation.get("failure_evidence_saved") is not True
            or implementation.get("real_model_called_during_runner_validation")
            is not False
        ):
            raise Q06RealRevalidationPlanError(
                "guarded runner must be implemented and offline validated"
            )
        checks.append("guarded_runner_is_offline_validated")

    is_authorized = candidate.get("status") == (
        "frozen_guarded_runner_offline_validated_and_real_call_"
        "authorized_pending_execution"
    )
    if is_authorized:
        compatible = candidate.get("compatible_authorization", {})
        if (
            compatible.get("status") != "authorized_by_user"
            or compatible.get("question_ids") != ["Q06"]
            or compatible.get("model") != "deepseek-v4-pro"
            or compatible.get("response_attempt_upper_bound") != 3
            or compatible.get("automatic_retry_count") != 0
            or compatible.get("authorization_matches_frozen_plan") is not True
        ):
            raise Q06RealRevalidationPlanError(
                "compatible authorization must exactly match the frozen plan"
            )
        checks.append("separate_authorization_matches_frozen_plan")

    is_failed_real_run = candidate.get("status") == (
        "frozen_real_revalidation_failed_after_three_responses_"
        "extra_tool_call_pending_user_decision"
    )
    if is_failed_real_run:
        compatible = candidate.get("compatible_authorization", {})
        real_run = candidate.get("real_validation", {})
        if (
            compatible.get("status") != "consumed_by_failed_run"
            or compatible.get("actual_response_attempts") != 3
            or compatible.get("unused_attempt_capacity_not_reusable") != 0
            or real_run.get("status")
            != "failed_after_three_completed_responses"
            or real_run.get("actual_response_attempts") != 3
            or real_run.get("failed_transport_attempts") != 0
            or real_run.get("third_observed_tool") != "get_data_profile"
            or real_run.get("extra_tool_executed") is not False
            or real_run.get("automatic_retry_performed") is not False
            or real_run.get("additional_real_call_authorized") is not False
        ):
            raise Q06RealRevalidationPlanError(
                "failed real run must consume all three responses and preserve stop evidence"
            )
        checks.append("failed_real_run_consumed_authority_and_stopped_extra_tool")

    return Q06RealRevalidationPreflight(
        status="passed",
        question_ids=("Q06",),
        model="deepseek-v4-pro",
        response_attempt_upper_bound=3,
        expected_beta_requests=3,
        automatic_retry_count=0,
        real_model_calls_allowed=is_authorized,
        checks=tuple(checks),
    )
