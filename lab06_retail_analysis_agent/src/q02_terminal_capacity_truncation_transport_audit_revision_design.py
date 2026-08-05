"""Offline validator for the Q02 terminal-capacity revision design."""

from __future__ import annotations

import json
from base64 import b64decode
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = (
    PROJECT_ROOT
    / "config"
    / "h3_q02_terminal_capacity_truncation_transport_audit_revision_design.candidate.json"
)


class Q02TerminalRevisionDesignError(ValueError):
    """Raised when the offline design widens scope or drifts from evidence."""


@dataclass(frozen=True)
class Q02TerminalRevisionDesignPreview:
    passed: bool
    observed_finish_reason: str
    observed_completion_tokens: int
    observed_content_characters: int
    proposed_report_terminal_max_tokens: int
    proposed_primary_stop_code: str
    proposed_not_evaluated_checks: tuple[str, ...]
    proposed_transport_mode: str
    response_counts: dict[str, int]
    source_files_unchanged: bool
    implementation_performed: bool
    real_model_called: bool
    network_used: bool
    api_key_read: bool


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Q02TerminalRevisionDesignError(
            f"JSON object required: {path.name}"
        )
    return value


def _hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _provider_payload(saved_http_response: dict[str, Any]) -> dict[str, Any]:
    encoded = saved_http_response.get("content_base64")
    if not isinstance(encoded, str):
        raise Q02TerminalRevisionDesignError(
            "saved HTTP response has no base64 provider payload"
        )
    try:
        payload = json.loads(b64decode(encoded).decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise Q02TerminalRevisionDesignError(
            "saved HTTP provider payload cannot be decoded"
        ) from exc
    if not isinstance(payload, dict):
        raise Q02TerminalRevisionDesignError(
            "decoded provider payload must be a JSON object"
        )
    return payload


def load_q02_terminal_revision_design() -> dict[str, Any]:
    return _read_json(CONTRACT_PATH)


def _source_path(source: dict[str, Any], field: str) -> Path:
    return PROJECT_ROOT / str(source[field])


def classify_terminal_response_candidate(
    *, expected_terminal_response: bool, finish_reason: str
) -> tuple[str, str] | None:
    """Preview the proposed pre-parse classification without changing runtime."""
    if finish_reason == "length":
        return ("model_response", "terminal_output_truncated")
    if expected_terminal_response:
        return None
    return None


def build_transport_audit_candidate(
    *, execution_mode: str, run_state: dict[str, Any]
) -> dict[str, Any]:
    allowed = {"offline_injected_transport", "real_transport"}
    if execution_mode not in allowed:
        raise Q02TerminalRevisionDesignError("unsupported execution mode")
    counts = {
        "attempted": int(run_state.get("attempted", 0)),
        "http_responses_received": int(
            run_state.get("http_responses_received", 0)
        ),
        "parsed_responses": int(run_state.get("parsed_responses", 0)),
        "failed_attempts": int(run_state.get("failed_attempts", 0)),
    }
    return {
        "execution_mode": execution_mode,
        "counts": counts,
        "real_network_opened": (
            execution_mode == "real_transport"
            and counts["http_responses_received"] > 0
        ),
        "real_model_response_received": (
            execution_mode == "real_transport"
            and counts["parsed_responses"] > 0
        ),
        "request_headers_saved": False,
        "request_body_saved": False,
        "authorization_header_value_saved": False,
        "api_key_value_saved": False,
        "api_key_source_saved": False,
    }


def validate_q02_terminal_revision_design(
    contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    value = contract or load_q02_terminal_revision_design()
    if value.get("status") not in {
        "candidate_pending_offline_validation_and_user_freeze",
        "candidate_offline_validated_pending_user_freeze",
        "frozen_by_user_offline_validated_pending_separate_implementation_authorization",
        "frozen_by_user_offline_implementation_authorized",
        "frozen_by_user_offline_implementation_completed",
    }:
        raise Q02TerminalRevisionDesignError("unexpected candidate status")

    source = value.get("source_evidence", {})
    saved_hash_pairs = (
        ("summary_path", "summary_sha256"),
        ("q02_case_path", "q02_case_sha256"),
        ("terminal_http_response_path", "terminal_http_response_sha256"),
    )
    implementation_hash_pairs = (
        ("deepseek_client_path", "deepseek_client_sha256"),
        ("batch_runner_path", "batch_runner_sha256"),
    )
    if any(
        _hash(_source_path(source, path_field)) != source.get(hash_field)
        for path_field, hash_field in saved_hash_pairs
    ):
        raise Q02TerminalRevisionDesignError(
            "saved Q02 evidence drifted"
        )
    implementation_authorized = value.get("status") in {
        "frozen_by_user_offline_implementation_authorized",
        "frozen_by_user_offline_implementation_completed",
    }
    if not implementation_authorized and any(
        _hash(_source_path(source, path_field)) != source.get(hash_field)
        for path_field, hash_field in implementation_hash_pairs
    ):
        raise Q02TerminalRevisionDesignError(
            "implementation source drifted before authorization"
        )

    summary = _read_json(_source_path(source, "summary_path"))
    case = _read_json(_source_path(source, "q02_case_path"))
    terminal_envelope = _read_json(
        _source_path(source, "terminal_http_response_path")
    )
    terminal = _provider_payload(terminal_envelope)
    choice = terminal["choices"][0]
    content = choice["message"]["content"]
    if (
        summary.get("status") != "failed_stopped"
        or summary.get("question_ids_executed") != ["Q02"]
        or summary.get("actual_response_attempts") != 2
        or summary.get("failed_transport_or_provider_attempts") != 0
        or choice.get("finish_reason") != "length"
        or terminal.get("usage", {}).get("completion_tokens") != 4096
        or len(content) != 11297
        or case.get("new_harness_validation", {}).get(
            "tool_reference_answer_status"
        ) != "passed"
    ):
        raise Q02TerminalRevisionDesignError(
            "saved Q02 truncation evidence no longer matches the design"
        )

    scope = value.get("scope", {})
    forbidden_true = (
        "h2_reference_answers_changed",
        "h2_validation_questions_changed",
        "prompt_changed",
        "tool_names_or_argument_schemas_changed",
        "report_schema_changed",
        "fact_schema_or_values_changed",
        "chart_schema_changed",
        "acceptance_root_rules_changed",
        "provider_endpoint_or_model_changed",
        "automatic_retry_added",
        "report_repair_added",
        "v2_2_3_resumed",
        "batch_b_authorized",
        "real_model_calls_allowed",
        "network_allowed",
        "api_key_may_be_read",
    )
    expected_implementation_performed = value.get("status") == (
        "frozen_by_user_offline_implementation_completed"
    )
    if (
        scope.get("offline_design_only") is not True
        or scope.get("implementation_performed")
        is not expected_implementation_performed
        or scope.get("design_policy_is_stage_based_not_q02_hardcoded")
        is not True
        or any(scope.get(field) is not False for field in forbidden_true)
        or scope.get("report_terminal_capacity_policy_applies_to")
        != [f"Q{index:02d}" for index in range(1, 8)]
        or scope.get("control_terminal_capacity_unchanged_for")
        != ["Q08", "Q09", "Q10"]
    ):
        raise Q02TerminalRevisionDesignError("candidate scope widened")

    capacity = value.get("boundary_1_terminal_output_capacity", {})
    if (
        capacity.get("selected_route") != "stage_specific_max_tokens"
        or capacity.get("request_field") != "max_tokens"
        or capacity.get("nonterminal_tool_selection_max_tokens") != 4096
        or capacity.get("report_terminal_max_tokens") != 8192
        or capacity.get("clarification_or_boundary_terminal_max_tokens")
        != 4096
        or capacity.get("observed_exhausted_limit") != 4096
        or capacity.get("selected_headroom_ratio") != 2
        or capacity.get("provider_documented_max_output_tokens", 0) < 8192
        or capacity.get("caller_must_explicitly_select_response_stage")
        is not True
        or capacity.get("unbounded_output_allowed") is not False
    ):
        raise Q02TerminalRevisionDesignError(
            "terminal capacity candidate drifted"
        )

    truncation = value.get("boundary_2_truncation_detection", {})
    if (
        truncation.get("selected_route")
        != "inspect_provider_finish_reason_before_terminal_json_parse"
        or truncation.get("primary_stop_stage") != "model_response"
        or truncation.get("primary_stop_code")
        != "terminal_output_truncated"
        or truncation.get("raw_provider_response_preserved") is not True
        or any(
            truncation.get(field) is not False
            for field in (
                "partial_json_repair_allowed",
                "schema_repair_allowed",
                "automatic_resume_allowed",
            )
        )
        or truncation.get("automatic_retry_count") != 0
    ):
        raise Q02TerminalRevisionDesignError(
            "truncation fail-closed rules drifted"
        )

    harness = value.get("boundary_3_harness_short_circuit", {})
    expected_not_evaluated = "not_evaluated_due_to_terminal_output_truncation"
    if (
        harness.get("primary_stop_codes") != ["terminal_output_truncated"]
        or harness.get("unexpected_terminal_status_may_also_be_primary")
        is not False
        or harness.get("tool_reference_answer_status_remains_independent")
        is not True
        or any(
            harness.get(field) != expected_not_evaluated
            for field in (
                "report_traceability_status",
                "report_completeness_status",
                "chart_acceptance_status",
            )
        )
        or harness.get("q02_chart_count_mismatch_may_be_appended")
        is not False
        or harness.get("not_evaluated_is_not_passed") is not True
        or harness.get("overall_question_status") != "failed_stopped"
    ):
        raise Q02TerminalRevisionDesignError(
            "Harness short-circuit candidate drifted"
        )

    transport = value.get("boundary_4_transport_audit_metadata", {})
    if (
        transport.get("execution_mode_source")
        != "ValidatedBatchAExecutionAuthority.mode"
        or transport.get("counter_source")
        != "BatchACrashSafeJournal.run_state"
        or transport.get("saved_q02_expected_mode") != "real_transport"
        or transport.get("saved_q02_expected_counts")
        != {
            "attempted": 2,
            "http_responses_received": 2,
            "parsed_responses": 2,
            "failed_attempts": 0,
        }
        or any(
            transport.get(field) is not False
            for field in (
                "request_headers_saved",
                "request_body_saved",
                "authorization_header_value_saved",
                "api_key_value_saved",
                "api_key_source_saved",
                "raw_customer_id_exported",
                "raw_retail_rows_exported",
            )
        )
    ):
        raise Q02TerminalRevisionDesignError(
            "transport audit candidate drifted"
        )

    authority = value.get("authorization", {})
    decision = value.get("decision_required", {})
    expected_implementation_allowed = value.get("status") == (
        "frozen_by_user_offline_implementation_authorized"
    )
    if (
        authority.get("implementation_allowed")
        is not expected_implementation_allowed
        or any(
            authority.get(field) is not False
            for field in (
                "real_model_calls_allowed",
                "batch_a_remaining_questions_authorized",
                "batch_b_authorized",
                "v2_2_3_may_resume",
            )
        )
    ) or not all(
        decision.get(field) is True
        for field in (
            "user_freeze_required",
            "separate_implementation_authorization_required",
            "separate_real_validation_authorization_required",
            "freeze_does_not_authorize_implementation",
            "freeze_does_not_authorize_real_calls",
        )
    ):
        raise Q02TerminalRevisionDesignError(
            "authorization or decision boundary widened"
        )
    if value.get("status") in {
        "frozen_by_user_offline_validated_pending_separate_implementation_authorization",
        "frozen_by_user_offline_implementation_authorized",
        "frozen_by_user_offline_implementation_completed",
    }:
        freeze = value.get("user_freeze", {})
        if (
            authority.get("design_frozen_by_user") is not True
            or freeze.get("status") != "frozen_by_user"
            or freeze.get("frozen_boundaries")
            != [
                "stage_specific_max_tokens_4096_8192_4096",
                "finish_reason_length_before_terminal_json_parse",
                "terminal_truncation_root_before_report_and_chart_acceptance",
                "authority_mode_plus_crash_safe_journal_counters",
            ]
            or not all(
                freeze.get(field) is True
                for field in (
                    "freeze_does_not_authorize_implementation",
                    "freeze_does_not_authorize_real_model_calls",
                    "h2_prompt_data_and_schemas_remain_frozen_unchanged",
                    "acceptance_root_rules_remain_unchanged",
                    "automatic_retry_count_remains_zero",
                    "batch_a_remaining_questions_not_authorized",
                    "batch_b_not_authorized",
                    "v2_2_3_remains_paused",
                )
            )
        ):
            raise Q02TerminalRevisionDesignError(
                "user-freeze boundary is incomplete or widened"
            )
    if value.get("status") == (
        "frozen_by_user_offline_implementation_completed"
    ):
        completed = value.get("offline_implementation_result", {})
        consumed = value.get("offline_implementation_authorization", {})
        if (
            consumed.get("status")
            != "authorized_by_user_and_consumed_by_completed_offline_stage"
            or completed.get("status") != "completed"
            or completed.get("implementation_performed") is not True
            or any(
                completed.get(field) is not False
                for field in (
                    "real_model_called",
                    "network_used",
                    "api_key_read",
                    "batch_b_authorized",
                    "v2_2_3_resumed",
                )
            )
        ):
            raise Q02TerminalRevisionDesignError(
                "completed offline implementation evidence is incomplete"
            )
    return value


def compile_q02_terminal_revision_preview(
) -> Q02TerminalRevisionDesignPreview:
    contract = validate_q02_terminal_revision_design()
    source = contract["source_evidence"]
    terminal = _provider_payload(
        _read_json(_source_path(source, "terminal_http_response_path"))
    )
    choice = terminal["choices"][0]
    classification = classify_terminal_response_candidate(
        expected_terminal_response=True,
        finish_reason=str(choice["finish_reason"]),
    )
    run_state_path = (
        _source_path(source, "summary_path").parent / "run_state.json"
    )
    audit = build_transport_audit_candidate(
        execution_mode="real_transport",
        run_state=_read_json(run_state_path),
    )
    source_hashes_unchanged = all(
        _hash(_source_path(source, path_field)) == source[hash_field]
        for path_field, hash_field in (
            ("summary_path", "summary_sha256"),
            ("q02_case_path", "q02_case_sha256"),
            ("terminal_http_response_path", "terminal_http_response_sha256"),
        )
    )
    no_calls = contract["scope"]
    return Q02TerminalRevisionDesignPreview(
        passed=(
            classification == ("model_response", "terminal_output_truncated")
            and audit["execution_mode"] == "real_transport"
            and audit["real_network_opened"]
            and audit["real_model_response_received"]
            and source_hashes_unchanged
        ),
        observed_finish_reason=str(choice["finish_reason"]),
        observed_completion_tokens=int(
            terminal["usage"]["completion_tokens"]
        ),
        observed_content_characters=len(choice["message"]["content"]),
        proposed_report_terminal_max_tokens=int(
            contract["boundary_1_terminal_output_capacity"][
                "report_terminal_max_tokens"
            ]
        ),
        proposed_primary_stop_code=str(classification[1]),
        proposed_not_evaluated_checks=(
            "report_traceability",
            "report_completeness",
            "chart_acceptance",
        ),
        proposed_transport_mode=str(audit["execution_mode"]),
        response_counts=dict(audit["counts"]),
        source_files_unchanged=source_hashes_unchanged,
        implementation_performed=bool(no_calls["implementation_performed"]),
        real_model_called=False,
        network_used=False,
        api_key_read=False,
    )


def negative_probe_contracts() -> list[dict[str, Any]]:
    """Return deliberate invalid designs for the formal offline validator."""
    base = load_q02_terminal_revision_design()
    probes: list[dict[str, Any]] = []
    for section, field, value in (
        ("scope", "prompt_changed", True),
        ("scope", "report_schema_changed", True),
        ("scope", "real_model_calls_allowed", True),
        ("authorization", "batch_a_remaining_questions_authorized", True),
        ("boundary_1_terminal_output_capacity", "report_terminal_max_tokens", 384000),
        ("boundary_2_truncation_detection", "partial_json_repair_allowed", True),
        ("boundary_2_truncation_detection", "automatic_retry_count", 1),
        ("boundary_3_harness_short_circuit", "q02_chart_count_mismatch_may_be_appended", True),
        ("boundary_4_transport_audit_metadata", "api_key_source_saved", True),
    ):
        changed = deepcopy(base)
        changed[section][field] = value
        probes.append(changed)
    return probes
