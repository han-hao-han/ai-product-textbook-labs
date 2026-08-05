"""Offline-only design validator for the Q02 failure/Harness revision."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from src.agent_orchestrator import (
    AgentTurnOutcome,
    ExecutedToolCall,
    RetailAgentOrchestrator,
)
from src.agent_protocol import FinalReportResponse, parse_control_response
from src.evidence_provenance import (
    RequestRecord,
    extract_request_records,
    frozen_policy_records,
)
from src.fact_schema import FactRecord
from src.fixed_question_validation import validate_fixed_question
from src.report_validation import validate_report


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = (
    PROJECT_ROOT
    / "config"
    / "h3_q02_failure_harness_revision_design.candidate.json"
)
CORE_SOURCE_PATHS = (
    PROJECT_ROOT / "src" / "agent_orchestrator.py",
    PROJECT_ROOT / "src" / "fixed_question_validation.py",
    PROJECT_ROOT / "src" / "q01_q10_batch_a_safe_runner.py",
    PROJECT_ROOT / "src" / "report_validation.py",
    PROJECT_ROOT / "src" / "report_evidence_semantic_boundary_v2_2_2.py",
    PROJECT_ROOT / "src" / "fact_schema.py",
    PROJECT_ROOT / "src" / "fact_builder.py",
    PROJECT_ROOT / "config" / "h2_validation_questions.json",
    PROJECT_ROOT / "data" / "raw" / "h2_reference_answers.json",
    PROJECT_ROOT / "prompts" / "agent_system_prompt_v1.md",
    PROJECT_ROOT / "prompts" / "report_prompt_v1.md",
)
EXPECTED_ROOT_CODES = [
    "untraceable_numeric_token",
    "unsupported_average_value_claim",
    "unsupported_average_value_claim",
]


class Q02FailureHarnessRevisionDesignError(ValueError):
    """Raised when the offline-only candidate design drifts."""


@dataclass(frozen=True)
class Q02FailureHarnessDesignPreview:
    root_failure_codes: tuple[str, ...]
    current_manifest_total: int
    current_manifest_covered: int
    retained_manifest_total: int
    retained_manifest_covered: int
    candidate_manifest_total: int
    candidate_manifest_covered: int
    candidate_metric_mapping_covered: bool
    saved_chart_requests: int
    buildable_saved_charts: int
    current_stop_reason: str
    candidate_primary_stop_stage: str
    source_hashes_before: dict[str, str]
    source_hashes_after: dict[str, str]
    source_files_unchanged: bool
    implementation_performed: bool
    real_model_called: bool
    network_used: bool
    api_key_read: bool


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Q02FailureHarnessRevisionDesignError(
            f"JSON object required: {path.name}"
        )
    return value


def _hash_sources() -> dict[str, str]:
    return {
        path.relative_to(PROJECT_ROOT).as_posix(): sha256(
            path.read_bytes()
        ).hexdigest()
        for path in CORE_SOURCE_PATHS
    }


def load_q02_failure_harness_revision_design() -> dict[str, Any]:
    return _read_json(CONTRACT_PATH)


def validate_q02_failure_harness_revision_design(
    contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    value = contract or load_q02_failure_harness_revision_design()
    if value.get("status") not in {
        "offline_design_pending_validation_and_user_freeze",
        "offline_validated_pending_user_freeze",
        "frozen_by_user_offline_validated_not_implemented",
    }:
        raise Q02FailureHarnessRevisionDesignError(
            "unexpected Q02 revision design status"
        )
    prerequisite = value.get("prerequisite", {})
    case_path = PROJECT_ROOT / str(
        prerequisite.get("case_evidence_path", "")
    )
    summary_path = PROJECT_ROOT / str(
        prerequisite.get("summary_evidence_path", "")
    )
    if (
        prerequisite.get("real_run_status") != "failed_stopped"
        or prerequisite.get("failed_question_id") != "Q02"
        or prerequisite.get("root_failure_stage") != "report_validation"
        or prerequisite.get("root_failure_codes") != EXPECTED_ROOT_CODES
        or not case_path.is_file()
        or not summary_path.is_file()
    ):
        raise Q02FailureHarnessRevisionDesignError(
            "Q02 real evidence prerequisite drifted"
        )
    case = _read_json(case_path)
    summary = _read_json(summary_path)
    if (
        case.get("question_id") != "Q02"
        or case.get("program_status") != "failed_stopped"
        or case.get("outcome", {}).get("error_stage")
        != "report_validation"
        or summary.get("status") != "failed_stopped"
        or summary.get("stop_reason") != "unexpected_terminal_status"
    ):
        raise Q02FailureHarnessRevisionDesignError(
            "saved Q02 failure evidence drifted"
        )
    scope = value.get("scope", {})
    if (
        scope.get("offline_design_only") is not True
        or scope.get("implementation_performed") is not False
        or scope.get("real_model_calls_allowed") is not False
        or scope.get("network_allowed") is not False
        or scope.get("api_key_may_be_read") is not False
        or any(
            scope.get(field) is not False
            for field in (
                "h2_reference_answers_changed",
                "h2_validation_questions_changed",
                "prompt_changed",
                "tool_names_or_argument_schemas_changed",
                "fact_schema_or_builder_changed",
                "report_validation_rules_changed",
                "average_value_rule_changed",
                "analysis_scope_row_count_rule_changed",
                "v2_2_3_resumed",
            )
        )
    ):
        raise Q02FailureHarnessRevisionDesignError(
            "offline design scope drifted"
        )
    rejected = value.get("boundary_1_rejected_report_evidence", {})
    if (
        rejected.get("selected_route")
        != "separate_non_publishable_rejected_report_evidence"
        or rejected.get("publishable") is not False
        or rejected.get("charts_materialized") is not False
        or rejected.get("accepted_report_fields_remain_empty_on_failure")
        is not True
        or rejected.get("rejected_evidence_may_be_used_for_diagnostics_only")
        is not True
        or rejected.get("rejected_evidence_may_not_be_exported_as_final_report")
        is not True
    ):
        raise Q02FailureHarnessRevisionDesignError(
            "rejected report evidence boundary drifted"
        )
    short_circuit = value.get(
        "boundary_2_upstream_failure_short_circuit", {}
    )
    if (
        short_circuit.get("root_dimension") != "report_traceability"
        or short_circuit.get("root_dimension_status") != "failed"
        or short_circuit.get("formal_downstream_status")
        != "not_evaluated_due_to_upstream_report_validation_failure"
        or short_circuit.get("downstream_dimensions")
        != ["report_completeness", "chart_acceptance"]
        or short_circuit.get("diagnostic_manifest_allowed") is not True
        or short_circuit.get("diagnostic_manifest_changes_acceptance_status")
        is not False
        or short_circuit.get("not_evaluated_is_not_passed") is not True
        or short_circuit.get("overall_question_status_remains_failed")
        is not True
    ):
        raise Q02FailureHarnessRevisionDesignError(
            "upstream failure short-circuit boundary drifted"
        )
    mapping = value.get("boundary_3_request_display_mapping", {})
    if (
        mapping.get("matching_route")
        != "exact_request_reference_plus_controlled_display_alias"
        or mapping.get("matching_request_reference_required") is not True
        or mapping.get("literal_internal_value_in_report_required")
        is not False
        or mapping.get("fuzzy_matching_allowed") is not False
        or mapping.get("model_judgment_allowed") is not False
        or mapping.get("q02_expected_diagnostic_manifest_before_mapping")
        != {"total": 27, "covered": 26}
        or mapping.get("q02_expected_diagnostic_manifest_after_mapping")
        != {"total": 27, "covered": 27}
        or mapping.get("alias_without_matching_request_reference_is_not_coverage")
        is not True
        or mapping.get("request_reference_without_alias_or_literal_is_not_coverage")
        is not True
    ):
        raise Q02FailureHarnessRevisionDesignError(
            "REQUEST display mapping boundary drifted"
        )
    priority = value.get("boundary_4_root_cause_priority", {})
    if (
        priority.get("q02_primary_stop_stage") != "report_validation"
        or priority.get("q02_primary_stop_codes") != EXPECTED_ROOT_CODES
        or priority.get("q02_acceptance_consequences")
        != [
            "unexpected_terminal_status",
            "new_harness_deterministic_acceptance_failed",
        ]
        or priority.get("q02_not_evaluated_checks")
        != ["report_completeness", "chart_acceptance"]
        or priority.get("legacy_stop_reason_candidate")
        != "report_validation_failed"
        or priority.get("automatic_retry_count") != 0
        or priority.get("automatic_resume_allowed") is not False
    ):
        raise Q02FailureHarnessRevisionDesignError(
            "root-cause priority boundary drifted"
        )
    expected = value.get("expected_q02_state_after_future_implementation", {})
    if (
        expected.get("overall_status") != "failed_stopped"
        or expected.get("tool_reference_answer_status") != "passed"
        or expected.get("report_traceability_status") != "failed"
        or expected.get("report_root_failure_count") != 3
        or expected.get("diagnostic_manifest")
        != {"total": 27, "covered": 27}
        or expected.get("buildable_saved_chart_request_count") != 1
        or expected.get("real_model_result_changed_to_pass") is not False
    ):
        raise Q02FailureHarnessRevisionDesignError(
            "expected Q02 post-implementation state drifted"
        )
    authorization = value.get("authorization", {})
    frozen = (
        value.get("status")
        == "frozen_by_user_offline_validated_not_implemented"
    )
    if (
        authorization.get("candidate_is_not_frozen") is not (not frozen)
        or authorization.get("design_frozen_by_user") is not frozen
        or authorization.get("implementation_allowed") is not False
        or authorization.get("real_model_calls_allowed") is not False
        or authorization.get("v2_2_3_may_resume") is not False
    ):
        raise Q02FailureHarnessRevisionDesignError(
            "design authorization boundary drifted"
        )
    if frozen:
        user_freeze = value.get("user_freeze", {})
        if (
            user_freeze.get("status") != "frozen_by_user"
            or user_freeze.get("frozen_on") != "2026-08-03"
            or user_freeze.get("frozen_boundaries")
            != [
                "separate_non_publishable_rejected_report_evidence",
                "upstream_failure_short_circuit_with_not_evaluated_status",
                "exact_request_reference_plus_controlled_display_alias",
                "outcome_root_cause_before_acceptance_consequences",
            ]
            or user_freeze.get("freeze_does_not_authorize_implementation")
            is not True
            or user_freeze.get("freeze_does_not_authorize_real_model_calls")
            is not True
            or user_freeze.get("h2_reference_answers_remain_frozen_unchanged")
            is not True
            or user_freeze.get("prompt_and_schema_remain_frozen_unchanged")
            is not True
            or user_freeze.get("report_root_failures_remain_unchanged")
            is not True
            or user_freeze.get("average_value_and_row_count_rules_remain_unchanged")
            is not True
            or user_freeze.get("batch_a_remaining_questions_not_authorized")
            is not True
            or user_freeze.get("v2_2_3_remains_paused") is not True
        ):
            raise Q02FailureHarnessRevisionDesignError(
                "frozen Q02 revision design drifted or grants authority"
            )
        freeze_validation = value.get("freeze_validation", {})
        freeze_evidence_path = PROJECT_ROOT / str(
            freeze_validation.get("evidence_path", "")
        )
        if (
            freeze_validation.get("status") != "passed"
            or freeze_validation.get("candidate_result")
            != "design_ready_not_implemented"
            or freeze_validation.get("root_failure_count") != 3
            or freeze_validation.get("expected_q02_status_remains")
            != "failed_stopped"
            or freeze_validation.get("candidate_manifest")
            != {"total": 27, "covered": 27}
            or freeze_validation.get("implementation_performed") is not False
            or freeze_validation.get("real_model_called") is not False
            or freeze_validation.get("network_used") is not False
            or freeze_validation.get("api_key_read") is not False
            or not freeze_evidence_path.is_file()
        ):
            raise Q02FailureHarnessRevisionDesignError(
                "frozen design validation evidence drifted"
            )
        saved_freeze = _read_json(freeze_evidence_path)
        if (
            saved_freeze.get("run_id")
            != freeze_validation.get("run_id")
            or saved_freeze.get("status") != "passed"
            or saved_freeze.get("candidate_result")
            != "design_ready_not_implemented"
            or saved_freeze.get("root_failure_codes")
            != EXPECTED_ROOT_CODES
            or saved_freeze.get("implementation_performed") is not False
            or saved_freeze.get("real_model_called") is not False
            or saved_freeze.get("network_used") is not False
            or saved_freeze.get("api_key_read_from_environment") is not False
        ):
            raise Q02FailureHarnessRevisionDesignError(
                "saved frozen design evidence drifted"
            )
    if value.get("status") in {
        "offline_validated_pending_user_freeze",
        "frozen_by_user_offline_validated_not_implemented",
    }:
        offline = value.get("offline_validation", {})
        evidence_path = PROJECT_ROOT / str(
            offline.get("evidence_path", "")
        )
        if (
            offline.get("status") != "passed"
            or offline.get("candidate_result")
            != "design_ready_not_implemented"
            or offline.get("root_failure_codes") != EXPECTED_ROOT_CODES
            or offline.get("current_manifest")
            != {"total": 27, "covered": 0}
            or offline.get("retained_manifest")
            != {"total": 27, "covered": 26}
            or offline.get("candidate_manifest")
            != {"total": 27, "covered": 27}
            or offline.get("buildable_saved_chart_count") != 1
            or offline.get("source_files_unchanged") is not True
            or offline.get("implementation_performed") is not False
            or offline.get("real_model_called") is not False
            or offline.get("network_used") is not False
            or offline.get("api_key_read") is not False
            or not evidence_path.is_file()
        ):
            raise Q02FailureHarnessRevisionDesignError(
                "offline design evidence drifted"
            )
    return value


def _reconstruct(case: dict[str, Any]) -> tuple[
    dict[str, Any],
    FinalReportResponse,
    tuple[FactRecord, ...],
    tuple[ExecutedToolCall, ...],
    tuple[RequestRecord, ...],
]:
    raw_outcome = case["outcome"]
    content = raw_outcome["raw_responses"][1]["choices"][0]["message"][
        "content"
    ]
    control = parse_control_response(content)
    if not isinstance(control, FinalReportResponse):
        raise Q02FailureHarnessRevisionDesignError(
            "Q02 terminal response is not a report"
        )
    facts = tuple(
        FactRecord.model_validate(item) for item in raw_outcome["facts"]
    )
    calls = tuple(
        ExecutedToolCall(
            call_id=item["call_id"],
            provider_call_id=item["provider_call_id"],
            tool_name=item["tool_name"],
            arguments=item["arguments"],
            result_path=item["result_path"],
            result=item["result"],
            facts=tuple(
                FactRecord.model_validate(fact)
                for fact in item["facts"]
            ),
        )
        for item in raw_outcome["tool_calls"]
    )
    requests = tuple(
        extract_request_records(
            raw_outcome["original_question"],
            session_id=raw_outcome["session_id"],
            turn_id=raw_outcome["turn_id"],
        )
    )
    return raw_outcome, control, facts, calls, requests


def _candidate_metric_mapping_covered(
    control: FinalReportResponse,
    requests: tuple[RequestRecord, ...],
    aliases: dict[str, list[str]],
) -> bool:
    request_by_id = {item.request_id: item for item in requests}
    for section in control.report.sections:
        for claim in section.claims:
            for reference in claim.evidence:
                request_id = getattr(reference, "request_id", None)
                record = request_by_id.get(request_id)
                if (
                    record is None
                    or record.parameter_name != "metric"
                    or record.value != "sales_amount_gbp"
                ):
                    continue
                if record.value in claim.statement or any(
                    alias in claim.statement
                    for alias in aliases[record.value]
                ):
                    return True
    return False


def compile_q02_failure_harness_design_preview(
) -> Q02FailureHarnessDesignPreview:
    contract = validate_q02_failure_harness_revision_design()
    source_hashes_before = _hash_sources()
    prerequisite = contract["prerequisite"]
    case = _read_json(
        PROJECT_ROOT / prerequisite["case_evidence_path"]
    )
    summary = _read_json(
        PROJECT_ROOT / prerequisite["summary_evidence_path"]
    )
    raw_outcome, control, facts, calls, requests = _reconstruct(case)
    policies = tuple(frozen_policy_records())
    report_validation = validate_report(
        control.report,
        list(facts),
        list(requests),
        list(policies),
    )
    diagnostic_outcome = AgentTurnOutcome(
        status="failed",
        session_id=raw_outcome["session_id"],
        turn_id=raw_outcome["turn_id"],
        original_question=raw_outcome["original_question"],
        model_response_count=raw_outcome["model_response_count"],
        tool_calls=calls,
        facts=facts,
        report_draft=control.report,
        report_validation=report_validation,
        raw_responses=tuple(raw_outcome["raw_responses"]),
        request_records=requests,
        policy_records=policies,
        error_stage="report_validation",
        error_message=raw_outcome["error_message"],
    )
    retained = validate_fixed_question("Q02", diagnostic_outcome)
    current_manifest = case["new_harness_validation"][
        "evidence_manifest"
    ]
    mapping = contract["boundary_3_request_display_mapping"]
    metric_covered = _candidate_metric_mapping_covered(
        control,
        requests,
        mapping["aliases"],
    )
    candidate_covered = sum(
        item.covered for item in retained.evidence_manifest
    )
    retained_covered = candidate_covered - int(metric_covered)
    buildable_charts = RetailAgentOrchestrator._build_charts(
        control.chart_requests,
        list(calls),
    )
    source_hashes_after = _hash_sources()
    return Q02FailureHarnessDesignPreview(
        root_failure_codes=tuple(
            item.code for item in report_validation.issues
        ),
        current_manifest_total=len(current_manifest),
        current_manifest_covered=sum(
            bool(item["covered"]) for item in current_manifest
        ),
        retained_manifest_total=len(retained.evidence_manifest),
        retained_manifest_covered=retained_covered,
        candidate_manifest_total=len(retained.evidence_manifest),
        candidate_manifest_covered=candidate_covered,
        candidate_metric_mapping_covered=metric_covered,
        saved_chart_requests=len(control.chart_requests),
        buildable_saved_charts=len(buildable_charts),
        current_stop_reason=summary["stop_reason"],
        candidate_primary_stop_stage="report_validation",
        source_hashes_before=source_hashes_before,
        source_hashes_after=source_hashes_after,
        source_files_unchanged=(
            source_hashes_before == source_hashes_after
        ),
        implementation_performed=False,
        real_model_called=False,
        network_used=False,
        api_key_read=False,
    )
