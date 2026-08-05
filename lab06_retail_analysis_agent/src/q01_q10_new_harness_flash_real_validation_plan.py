"""Offline validation for the Q01-Q10 new-Harness Flash plan."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = (
    PROJECT_ROOT
    / "config"
    / "h3_q01_q10_new_harness_flash_real_validation_plan.candidate.json"
)


class Q01Q10NewHarnessFlashPlanError(ValueError):
    """Raised when the offline real-validation design drifts."""


@dataclass(frozen=True)
class Q01Q10NewHarnessFlashPlanPreflight:
    status: str
    model: str
    batch_a_question_ids: tuple[str, ...]
    batch_b_question_ids: tuple[str, ...]
    batch_a_attempt_cap: int
    batch_b_attempt_cap: int
    total_attempt_cap: int
    automatic_retry_count: int
    real_model_calls_allowed: bool
    guarded_runner_ready: bool
    checks: tuple[str, ...]


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Q01Q10NewHarnessFlashPlanError(
            f"{path.name} must be a JSON object"
        )
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_q01_q10_new_harness_flash_plan() -> dict[str, Any]:
    return _read_object(PLAN_PATH)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Q01Q10NewHarnessFlashPlanError(message)


def validate_q01_q10_new_harness_flash_plan(
    plan: dict[str, Any] | None = None,
) -> Q01Q10NewHarnessFlashPlanPreflight:
    candidate = deepcopy(plan) if plan is not None else load_q01_q10_new_harness_flash_plan()
    checks: list[str] = []
    _require(
        candidate.get("status")
        in {
            "candidate_pending_offline_validation_and_user_freeze",
            "candidate_offline_validated_pending_user_freeze",
            "frozen_by_user_pending_guarded_runner_design_and_separate_batch_authorization",
        },
        "unexpected design status",
    )

    prerequisites = candidate.get("prerequisites", {})
    harness = _read_object(
        PROJECT_ROOT / prerequisites.get("new_harness_contract", "")
    )
    _require(
        harness.get("status")
        == prerequisites.get("required_new_harness_status")
        == "offline_implementation_validated_pending_user_checkpoint",
        "new Harness prerequisite is missing or drifted",
    )
    _require(
        prerequisites.get("h2_questions_status") == "frozen_by_user"
        and prerequisites.get("v2_2_3_required_status")
        == "paused_by_user_pending_q01_q10_acceptance_harness_audit"
        and "Q01至Q10均" in prerequisites.get("current_new_harness_real_status", ""),
        "frozen H2, paused V2.2.3, or unknown real-status boundary drifted",
    )
    checks.append("new_harness_h2_and_v2_2_3_prerequisites_are_exact")

    expected_ids = [f"Q{index:02d}" for index in range(1, 11)]
    scope = candidate.get("scope", {})
    _require(
        scope.get("question_ids") == expected_ids
        and scope.get("model") == "deepseek-v4-flash"
        and scope.get("provider") == "DeepSeek",
        "question scope or model drifted",
    )
    unchanged_fields = (
        "prompt_changed",
        "provider_schema_changed",
        "control_schema_changed",
        "data_changed",
        "h2_reference_answers_changed",
        "seven_tool_whitelist_changed",
        "tool_argument_schemas_changed",
        "new_harness_acceptance_changed",
        "v2_2_3_resumed",
        "real_runner_implemented_in_design_stage",
    )
    _require(
        all(scope.get(field) is False for field in unchanged_fields),
        "frozen source or paused-stage scope drifted",
    )
    checks.append("scope_is_flash_only_and_frozen_inputs_remain_unchanged")

    protocol = candidate.get("request_protocol", {})
    _require(
        protocol.get("endpoint")
        == "https://api.deepseek.com/beta/chat/completions"
        and protocol.get("thinking") == {"type": "disabled"}
        and protocol.get("temperature") == 0
        and protocol.get("stream") is False
        and protocol.get("tool_choice_for_nonterminal_responses") == "auto"
        and protocol.get("tool_choice_for_terminal_response") == "none"
        and protocol.get("terminal_response_format") == {"type": "json_object"}
        and protocol.get("tool_visibility_per_response") == 7
        and protocol.get("parallel_requests") is False
        and protocol.get("automatic_retry_count") == 0,
        "request protocol drifted",
    )
    checks.append("native_tool_and_terminal_json_protocol_is_exact")

    arithmetic = candidate.get("response_arithmetic", {})
    questions = arithmetic.get("questions", [])
    expected_counts = {
        "Q01": 2,
        "Q02": 2,
        "Q03": 2,
        "Q04": 2,
        "Q05": 3,
        "Q06": 3,
        "Q07": 3,
        "Q08": 1,
        "Q09": 1,
        "Q10": 1,
    }
    _require(
        [item.get("question_id") for item in questions] == expected_ids
        and {
            item.get("question_id"): item.get("maximum_response_attempts")
            for item in questions
        }
        == expected_counts
        and sum(expected_counts.values()) == 20
        and arithmetic.get("single_tool_report_subtotal") == 8
        and arithmetic.get("multi_tool_report_subtotal") == 9
        and arithmetic.get("zero_tool_control_subtotal") == 3
        and arithmetic.get("all_questions_maximum_response_attempts") == 20
        and "HTTP请求前" in arithmetic.get("counting_rule", ""),
        "response-attempt arithmetic drifted",
    )
    checks.append("per_question_and_total_response_arithmetic_is_exact")

    batches = candidate.get("batches", [])
    _require(len(batches) == 2, "exactly two batches are required")
    batch_a, batch_b = batches
    expected_a = ["Q02", "Q06", "Q08", "Q09", "Q10"]
    expected_b = ["Q01", "Q03", "Q04", "Q05", "Q07"]
    _require(
        batch_a.get("batch_id") == "A"
        and batch_a.get("question_ids_in_order") == expected_a
        and batch_a.get("maximum_response_attempts") == 8
        and batch_a.get("automatic_retry_count") == 0
        and batch_a.get("must_stop_for_user_review_after_batch") is True
        and batch_a.get("authorizes_batch_b") is False,
        "batch A selection or cap drifted",
    )
    _require(
        batch_b.get("batch_id") == "B"
        and batch_b.get("question_ids_in_order") == expected_b
        and batch_b.get("maximum_response_attempts") == 12
        and batch_b.get("automatic_retry_count") == 0
        and batch_b.get("must_stop_for_user_review_after_batch") is True
        and batch_b.get("may_start_automatically_after_batch_a") is False,
        "batch B selection, cap, or checkpoint drifted",
    )
    _require(
        set(expected_a).isdisjoint(expected_b)
        and set(expected_a + expected_b) == set(expected_ids),
        "batch partition must cover Q01-Q10 exactly once",
    )
    checks.append("sentinel_and_remaining_batches_are_exact_and_disjoint")

    failure = candidate.get("failure_and_stop_rules", {})
    required_true = (
        "reserve_attempt_before_transport",
        "stop_current_batch_on_first_transport_failure",
        "stop_current_batch_on_first_provider_shape_failure",
        "stop_current_batch_on_first_schema_or_semantic_failure",
        "stop_current_batch_on_first_tool_or_dataflow_failure",
        "stop_current_batch_on_first_report_or_fixed_question_failure",
    )
    required_false = (
        "continue_to_later_question_after_failure",
        "unused_attempt_capacity_reusable",
        "authorization_reusable_after_run_or_failure",
        "automatic_resume_after_network_recovery",
    )
    _require(
        all(failure.get(field) is True for field in required_true)
        and all(failure.get(field) is False for field in required_false)
        and failure.get("automatic_retry_count") == 0
        and "重新授权" in failure.get("resume_rule", ""),
        "failure, network, or retry policy drifted",
    )
    checks.append("network_failure_counts_stops_and_requires_new_authority")

    acceptance = candidate.get("deterministic_acceptance", {})
    _require(
        acceptance.get("q01_q07_required_status")
        == "passed_deterministic_pending_manual_review"
        and acceptance.get("q08_q10_required_status")
        == "passed_deterministic_pending_manual_review"
        and acceptance.get("protocol_and_dataflow_passed_is_real_success") is False
        and acceptance.get("tool_reference_answers_must_match_h2") is True
        and acceptance.get("q01_q07_every_manifest_item_must_be_covered") is True
        and acceptance.get("allowed_report_evidence_source_types")
        == ["FACT", "REQUEST", "POLICY"]
        and acceptance.get("q10_required_boundary_codes")
        == ["forecasting_unsupported", "automatic_replenishment_unsupported"]
        and acceptance.get("transport_or_json_success_alone_is_success") is False
        and acceptance.get("batch_partial_pass_is_batch_pass") is False,
        "new Harness deterministic acceptance drifted",
    )
    manual = candidate.get("manual_review", {})
    _require(
        manual.get("required") is True
        and manual.get("automatic_deterministic_pass_does_not_complete_manual_review") is True
        and manual.get("fully_accepted_label_may_be_set_automatically") is False
        and manual.get("user_checkpoint_required_after_each_batch") is True,
        "manual review was weakened or automated",
    )
    checks.append("deterministic_and_manual_acceptance_remain_separate")

    evidence = candidate.get("evidence_and_privacy", {})
    required_evidence = (
        "save_locally_under_results_raw",
        "save_each_provider_raw_response",
        "save_each_failed_attempt",
        "save_parsed_control_or_tool_calls",
        "save_tool_results_facts_charts_and_report",
        "save_fixed_question_and_report_validation",
        "save_exact_reserved_attempt_count",
        "save_completed_response_count",
        "save_failed_transport_attempt_count",
        "save_provider_response_model_finish_reason_and_usage",
        "save_stop_stage_and_sanitized_error",
        "current_results_must_not_overwrite_prior_success",
    )
    forbidden_evidence = (
        "api_key_saved",
        "authorization_header_saved",
        "request_headers_saved",
        "request_body_saved",
        "raw_customer_id_exported",
        "raw_retail_rows_exported",
        "local_absolute_paths_saved",
    )
    _require(
        all(evidence.get(field) is True for field in required_evidence)
        and all(evidence.get(field) is False for field in forbidden_evidence),
        "evidence or privacy boundary drifted",
    )
    checks.append("success_failure_counting_and_privacy_evidence_are_complete")

    authorization = candidate.get("authorization", {})
    _require(
        authorization.get("status") == "not_authorized"
        and authorization.get("real_model_calls_allowed") is False
        and authorization.get("api_key_may_be_read_during_design") is False
        and authorization.get("network_may_be_opened_during_design") is False
        and authorization.get("freeze_does_not_authorize_real_calls") is True
        and authorization.get("batch_a_requires_separate_exact_authorization") is True
        and authorization.get("batch_b_requires_separate_exact_authorization") is True
        and authorization.get("batch_a_authorization_does_not_authorize_batch_b") is True
        and authorization.get("authorization_must_name_model") == "deepseek-v4-flash"
        and authorization.get("batch_a_authorization_must_name_question_ids") == expected_a
        and authorization.get("batch_a_authorization_must_name_response_attempt_upper_bound") == 8
        and authorization.get("batch_b_authorization_must_name_question_ids") == expected_b
        and authorization.get("batch_b_authorization_must_name_response_attempt_upper_bound") == 12
        and authorization.get("authorization_must_name_automatic_retry_count") == 0
        and authorization.get("authorization_checked_before_api_key_read") is True
        and authorization.get("one_authorization_allows_at_most_one_batch_execution") is True
        and authorization.get("authorization_consumed_when_first_outbound_attempt_is_reserved") is True,
        "authorization boundary drifted",
    )
    checks.append("freeze_and_two_batch_authorizations_are_strictly_separate")

    for relative, expected_hash in candidate.get("frozen_source_hashes", {}).items():
        _require(
            _sha256(PROJECT_ROOT / relative) == expected_hash,
            f"frozen source changed: {relative}",
        )
    checks.append("frozen_h2_prompt_harness_and_v2_2_3_hashes_match")

    implementation = candidate.get("implementation", {})
    runner_implemented = implementation.get("guarded_real_runner") == (
        "scripts/run_q01_q10_batch_a_flash_validation.py"
    )
    if runner_implemented:
        runner_authority = candidate.get(
            "offline_runner_implementation_authorization", {}
        )
        _require(
            implementation.get("guarded_real_runner_status")
            == "implemented_and_offline_validated_default_denied_pending_separate_real_authorization"
            and implementation.get("runner_contract")
            == "config/h3_q01_q10_batch_a_safe_runner_implementation.json"
            and runner_authority.get("status")
            == "authorized_by_user_and_consumed"
            and runner_authority.get("real_model_calls_authorized") is False
            and runner_authority.get("network_authorized") is False
            and runner_authority.get("api_key_read_authorized") is False
            and runner_authority.get("v2_2_3_resume_authorized") is False,
            "offline runner implementation lacks exact authority or evidence",
        )
    else:
        _require(
            implementation.get("guarded_real_runner")
            == "not_implemented_in_design_stage"
            and implementation.get("guarded_real_runner_status")
            == "pending_plan_freeze_and_separate_implementation_authorization",
            "unexpected runner implementation state",
        )
    _require(
        implementation.get("real_model_called_during_design") is False
        and implementation.get("network_used_during_design") is False
        and implementation.get("api_key_read_during_design") is False,
        "runner work cannot claim network, model call, or key access",
    )
    checks.append("runner_state_is_bounded_and_has_no_real_call_authority")

    if candidate.get("status").startswith("frozen_"):
        freeze = candidate.get("user_freeze", {})
        _require(
            freeze.get("status") == "frozen_by_user"
            and freeze.get("frozen_on") == "2026-08-03"
            and freeze.get("model") == "deepseek-v4-flash"
            and freeze.get("batch_a_question_ids") == expected_a
            and freeze.get("batch_a_response_attempt_upper_bound") == 8
            and freeze.get("batch_b_question_ids") == expected_b
            and freeze.get("batch_b_response_attempt_upper_bound") == 12
            and freeze.get("automatic_retry_count") == 0
            and freeze.get("stop_current_batch_on_first_failure") is True
            and freeze.get("manual_review_required_after_each_batch") is True
            and freeze.get("freeze_does_not_authorize_real_calls") is True
            and freeze.get("freeze_does_not_authorize_runner_implementation") is True
            and freeze.get("batch_a_requires_separate_real_authorization") is True
            and freeze.get("batch_b_requires_separate_real_authorization") is True
            and freeze.get("v2_2_3_remains_paused") is True,
            "user freeze record drifted or grants authority",
        )
        checks.append("user_freeze_is_exact_and_grants_no_execution_authority")

    return Q01Q10NewHarnessFlashPlanPreflight(
        status="passed",
        model="deepseek-v4-flash",
        batch_a_question_ids=tuple(expected_a),
        batch_b_question_ids=tuple(expected_b),
        batch_a_attempt_cap=8,
        batch_b_attempt_cap=12,
        total_attempt_cap=20,
        automatic_retry_count=0,
        real_model_calls_allowed=False,
        guarded_runner_ready=runner_implemented,
        checks=tuple(checks),
    )
