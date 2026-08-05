"""Validate the V2.2.1 single-Q06 Flash real revalidation design."""

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
    / "h3_q06_v2_2_1_flash_real_revalidation_plan.candidate.json"
)
TERMINAL_JSON_CONTRACT_PATH = (
    PROJECT_ROOT
    / "config"
    / "h3_report_terminal_json_boundary_v2_2_1.candidate.json"
)


class Q06V2_2_1FlashRealPlanError(ValueError):
    """Raised when the proposed real-validation plan drifts."""


@dataclass(frozen=True)
class Q06V2_2_1FlashRealPlanPreflight:
    status: str
    model: str
    question_ids: tuple[str, ...]
    response_attempt_upper_bound: int
    automatic_retry_count: int
    tool_choice_sequence: tuple[str, ...]
    response_format_sequence: tuple[dict[str, str] | None, ...]
    real_model_calls_allowed: bool
    guarded_runner_ready: bool
    checks: tuple[str, ...]


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Q06V2_2_1FlashRealPlanError(
            f"{path.name} must be a JSON object"
        )
    return value


def load_q06_v2_2_1_flash_real_plan() -> dict[str, Any]:
    return _read_object(PLAN_PATH)


def validate_q06_v2_2_1_flash_real_plan(
    plan: dict[str, Any] | None = None,
) -> Q06V2_2_1FlashRealPlanPreflight:
    candidate = (
        deepcopy(plan)
        if plan is not None
        else load_q06_v2_2_1_flash_real_plan()
    )
    checks: list[str] = []
    if candidate.get("status") not in {
        "candidate_pending_offline_validation_and_user_freeze",
        "candidate_offline_validated_pending_user_freeze",
        "frozen_pending_guarded_runner_implementation_and_separate_real_authorization",
        "frozen_guarded_runner_offline_validated_pending_separate_real_authorization",
        "frozen_guarded_runner_offline_validated_and_real_call_authorized_pending_execution",
        "frozen_real_validation_failed_pending_user_decision",
    }:
        raise Q06V2_2_1FlashRealPlanError(
            "design stage has an unexpected status"
        )

    terminal = _read_object(TERMINAL_JSON_CONTRACT_PATH)
    prerequisite = candidate.get("prerequisite", {})
    if (
        terminal.get("status")
        != "frozen_by_user_pending_separate_real_authorization"
        or prerequisite.get("required_status") != terminal.get("status")
        or prerequisite.get("required_offline_run_id")
        != terminal.get("offline_validation", {}).get("run_id")
        or prerequisite.get("default_model") != "deepseek-v4-flash"
    ):
        raise Q06V2_2_1FlashRealPlanError(
            "frozen V2.2.1 prerequisite is missing"
        )
    checks.append("frozen_v2_2_1_terminal_json_boundary_is_exact")

    scope = candidate.get("scope", {})
    if (
        scope.get("question_ids") != ["Q06"]
        or scope.get("model") != "deepseek-v4-flash"
        or scope.get("pro_calls_allowed") != 0
        or scope.get("other_q01_q10_calls_allowed") != 0
        or any(
            scope.get(field) is not False
            for field in (
                "prompt_changed",
                "provider_schema_changed",
                "control_schema_changed",
                "data_changed",
                "acceptance_rules_changed",
                "seven_tool_whitelist_changed",
                "h2_metrics_changed",
                "dsml_repair_added",
            )
        )
    ):
        raise Q06V2_2_1FlashRealPlanError("scope drifted")
    checks.append("q06_flash_only_without_frozen_input_changes")

    protocol = candidate.get("request_protocol", {})
    response_formats = protocol.get("response_format_sequence")
    if (
        protocol.get("endpoint")
        != "https://api.deepseek.com/beta/chat/completions"
        or protocol.get("tool_visibility_each_response") != [7, 7, 7]
        or protocol.get("tool_choice_sequence")
        != ["auto", "auto", "none"]
        or response_formats
        != [None, None, {"type": "json_object"}]
        or protocol.get("thinking") != {"type": "disabled"}
        or protocol.get("temperature") != 0
        or protocol.get("stream") is not False
        or protocol.get("maximum_expected_responses") != 3
        or protocol.get("maximum_business_tool_calls") != 2
        or protocol.get("parallel_requests") is not False
    ):
        raise Q06V2_2_1FlashRealPlanError("request protocol drifted")
    checks.append("auto_auto_none_and_terminal_json_protocol_is_exact")

    limits = candidate.get("hard_limits", {})
    required_limits = {
        "response_attempt_upper_bound": 3,
        "reserve_attempt_before_transport": True,
        "automatic_retry_count": 0,
        "stop_on_first_transport_failure": True,
        "stop_on_first_provider_or_parse_failure": True,
        "stop_on_first_schema_or_semantic_failure": True,
        "continue_after_empty_json_content": False,
        "continue_after_finish_reason_length": False,
        "continue_after_wrong_tool_or_arguments": False,
        "unused_attempt_capacity_reusable": False,
        "authorization_reusable_after_run": False,
    }
    if any(
        limits.get(key) != value
        for key, value in required_limits.items()
    ):
        raise Q06V2_2_1FlashRealPlanError("hard limits drifted")
    checks.append("three_attempts_zero_retry_and_failure_stop_are_exact")

    gates = candidate.get("response_gates", [])
    if (
        len(gates) != 3
        or [gate.get("response_index") for gate in gates] != [1, 2, 3]
        or [gate.get("expected_action") for gate in gates]
        != ["tool_call", "tool_call", "control_response"]
        or [gate.get("expected_tool") for gate in gates[:2]]
        != ["analyze_time_trend", "rank_products"]
        or gates[0].get("expected_provider_arguments", {}).get("start_date")
        != "__NONE__"
        or gates[0].get("expected_provider_arguments", {}).get("end_date")
        != "__NONE__"
        or gates[1].get("arguments_must_derive_from_peak_period_fact")
        is not True
        or gates[2].get("tool_calls_must_be_empty") is not True
        or gates[2].get("content_must_be_nonempty_json_object") is not True
        or gates[2].get("finish_reason_length_is_failure") is not True
        or gates[2].get("dsml_or_markdown_repair_allowed") is not False
        or gates[2].get("pydantic_control_schema_required") is not True
        or gates[2].get("fact_and_report_validation_required") is not True
    ):
        raise Q06V2_2_1FlashRealPlanError("response gates drifted")
    checks.append("three_response_gates_preserve_tool_and_json_boundaries")

    acceptance = candidate.get("program_acceptance", {})
    if (
        acceptance.get("expected_terminal_status") != "completed"
        or acceptance.get("expected_response_attempts") != 3
        or acceptance.get("expected_tool_sequence")
        != ["analyze_time_trend", "rank_products"]
        or acceptance.get("fixed_question_validation_required") is not True
        or acceptance.get("report_validation_required") is not True
        or acceptance.get("report_must_reference_both_calls") is not True
        or acceptance.get("chart_count") != 2
        or acceptance.get("chart_types")
        != ["monthly_line", "top_n_horizontal_bar"]
        or acceptance.get("raw_customer_id_must_not_appear") is not True
        or acceptance.get("manual_review_required") is not True
        or acceptance.get("program_pass_is_not_manual_acceptance") is not True
    ):
        raise Q06V2_2_1FlashRealPlanError("acceptance rules drifted")
    checks.append("program_and_manual_acceptance_are_separate")

    evidence = candidate.get("evidence", {})
    if (
        evidence.get("save_provider_raw_responses") is not True
        or evidence.get(
            "save_requested_tool_choice_and_response_format_per_response"
        )
        is not True
        or evidence.get("save_program_failures_and_exact_stop_stage")
        is not True
        or any(
            evidence.get(field) is not False
            for field in (
                "api_key_saved",
                "authorization_header_saved",
                "request_body_saved",
                "raw_customer_id_exported",
                "local_absolute_paths_saved",
            )
        )
    ):
        raise Q06V2_2_1FlashRealPlanError("evidence boundary drifted")
    checks.append("raw_success_failure_and_privacy_evidence_are_bounded")

    status = candidate.get("status")
    ready_statuses = {
        "frozen_guarded_runner_offline_validated_pending_separate_real_authorization",
        "frozen_guarded_runner_offline_validated_and_real_call_authorized_pending_execution",
        "frozen_real_validation_failed_pending_user_decision",
    }
    guarded_runner_ready = status in ready_statuses
    real_model_calls_allowed = status == (
        "frozen_guarded_runner_offline_validated_and_real_call_"
        "authorized_pending_execution"
    )
    authorization = candidate.get("authorization", {})
    if (
        authorization.get("freeze_does_not_authorize_real_calls")
        is not True
        or authorization.get("prior_v2_2_authorization_reusable") is not False
        or authorization.get("new_exact_user_authorization_required")
        is not True
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
        or authorization.get("authorization_must_be_validated_before_api_key_read")
        is not True
        or authorization.get("one_authorization_allows_at_most_one_runner_execution")
        is not True
    ):
        raise Q06V2_2_1FlashRealPlanError(
            "authorization boundary drifted"
        )
    if real_model_calls_allowed:
        if (
            authorization.get("status") != "authorized_by_user"
            or authorization.get("real_model_calls_allowed") is not True
            or authorization.get("authorization_matches_frozen_plan")
            is not True
            or authorization.get("authorized_question_ids") != ["Q06"]
            or authorization.get("authorized_model")
            != "deepseek-v4-flash"
            or authorization.get("authorized_response_attempt_upper_bound")
            != 3
            or authorization.get("authorized_automatic_retry_count") != 0
        ):
            raise Q06V2_2_1FlashRealPlanError(
                "authorized execution boundary is incomplete"
            )
    elif status == "frozen_real_validation_failed_pending_user_decision":
        real = candidate.get("real_validation", {})
        if (
            authorization.get("status") != "consumed_by_failed_run"
            or authorization.get("real_model_calls_allowed") is not False
            or authorization.get("actual_response_attempts") != 3
            or authorization.get("unused_attempt_capacity_reusable")
            is not False
            or real.get("status") != "failed_after_three_completed_responses"
            or real.get("actual_response_attempts") != 3
            or real.get("completed_model_responses") != 3
            or real.get("failed_transport_attempts") != 0
            or real.get("automatic_retry_count") != 0
            or real.get("terminal_json_parse_passed") is not True
            or real.get("control_schema_passed") is not True
            or real.get("report_validation_status") != "failed"
            or real.get("additional_real_call_authorized") is not False
        ):
            raise Q06V2_2_1FlashRealPlanError(
                "failed real-run evidence or consumed authority drifted"
            )
    elif (
        authorization.get("status") != "not_authorized"
        or authorization.get("real_model_calls_allowed") is not False
    ):
        raise Q06V2_2_1FlashRealPlanError(
            "non-authorized plan cannot allow real calls"
        )
    implementation = candidate.get("implementation", {})
    frozen = status.startswith("frozen_")
    if guarded_runner_ready:
        offline = candidate.get("runner_offline_validation", {})
        if (
            implementation.get("guarded_runner")
            != "scripts/run_q06_v2_2_1_flash_real_revalidation.py"
            or implementation.get("guarded_runner_status")
            != "implemented_and_offline_validated"
            or offline.get("status") != "passed"
            or offline.get("current_gate_blocked_before_api_key_read")
            is not True
            or offline.get("success_response_attempts") != 3
            or offline.get("success_tool_choices")
            != ["auto", "auto", "none"]
            or offline.get("success_response_formats")
            != [None, None, {"type": "json_object"}]
            or offline.get("failure_response_attempts") != 1
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
            raise Q06V2_2_1FlashRealPlanError(
                "guarded runner offline evidence is incomplete"
            )
    else:
        expected_runner_status = (
            "pending_guarded_runner_implementation"
            if frozen
            else "pending_plan_freeze"
        )
        if (
            implementation.get("guarded_runner")
            != "not_implemented_in_design_stage"
            or implementation.get("guarded_runner_status")
            != expected_runner_status
        ):
            raise Q06V2_2_1FlashRealPlanError(
                "design stage must not claim a runnable real runner"
            )
    if (
        implementation.get("real_model_called_during_design") is not False
        or implementation.get("api_key_read_during_design") is not False
    ):
        raise Q06V2_2_1FlashRealPlanError(
            "runner work must not claim real model or API key access"
        )
    if frozen:
        freeze = candidate.get("user_freeze", {})
        if (
            freeze.get("status") != "frozen_by_user"
            or freeze.get("question_ids") != ["Q06"]
            or freeze.get("model") != "deepseek-v4-flash"
            or freeze.get("response_attempt_upper_bound") != 3
            or freeze.get("automatic_retry_count") != 0
            or freeze.get("response_format_sequence")
            != [None, None, {"type": "json_object"}]
            or freeze.get("freeze_does_not_authorize_real_calls")
            is not True
            or freeze.get("freeze_does_not_claim_runner_ready") is not True
        ):
            raise Q06V2_2_1FlashRealPlanError(
                "frozen plan lacks the exact user-freeze boundary"
            )
    checks.append("runner_readiness_and_real_call_authority_are_separate")

    return Q06V2_2_1FlashRealPlanPreflight(
        status="passed",
        model="deepseek-v4-flash",
        question_ids=("Q06",),
        response_attempt_upper_bound=3,
        automatic_retry_count=0,
        tool_choice_sequence=("auto", "auto", "none"),
        response_format_sequence=(
            None,
            None,
            {"type": "json_object"},
        ),
        real_model_calls_allowed=real_model_calls_allowed,
        guarded_runner_ready=guarded_runner_ready,
        checks=tuple(checks),
    )
