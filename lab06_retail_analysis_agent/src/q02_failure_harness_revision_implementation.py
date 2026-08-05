"""Formal offline validation for the implemented Q02 failure boundaries."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from src.deepseek_client import ChatCompletionResult
from src.fixed_question_validation import load_frozen_questions
from src.mock_h2_registry import FrozenH2MockRegistry
from src.mock_native_tool_client_v2_1_revision import _tool_payloads
from src.native_tool_transport_mock_v2_1_revision import (
    OfflineNativeToolTransportV2_1Revision,
)
from src.q01_q10_batch_a_offline_mock import (
    BATCH_A_QUESTION_IDS,
    BatchAEvidenceCompleteMockClient,
)
from src.q01_q10_batch_a_safe_runner import (
    BATCH_A_OFFLINE_CONFIRMATION,
    execute_batch_a_validation,
    validate_offline_execution_request,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = (
    PROJECT_ROOT
    / "config"
    / "h3_q02_failure_harness_revision_implementation.json"
)
DESIGN_PATH = (
    PROJECT_ROOT
    / "config"
    / "h3_q02_failure_harness_revision_design.candidate.json"
)
SAVED_CASE_PATH = (
    PROJECT_ROOT
    / "results"
    / "raw"
    / "q01_q10_batch_a_flash_20260803T195956_363133+0800"
    / "Q02.json"
)
ROOT_CODES = [
    "untraceable_numeric_token",
    "unsupported_average_value_claim",
    "unsupported_average_value_claim",
]
NOT_EVALUATED = (
    "not_evaluated_due_to_upstream_report_validation_failure"
)
FROZEN_SOURCE_PATHS = (
    PROJECT_ROOT / "data" / "raw" / "h2_reference_answers.json",
    PROJECT_ROOT / "config" / "h2_validation_questions.json",
    PROJECT_ROOT / "config" / "h3_q01_q10_acceptance_harness_implementation.json",
    PROJECT_ROOT / "config" / "h3_q06_report_revision_feedback_boundary_v2_2_3.candidate.json",
    PROJECT_ROOT / "prompts" / "agent_system_prompt_v1.md",
    PROJECT_ROOT / "prompts" / "report_prompt_v1.md",
)


class Q02FailureHarnessRevisionImplementationError(ValueError):
    pass


@dataclass(frozen=True)
class Q02ImplementationValidationResult:
    passed: bool
    batch_run_id: str
    batch_summary: dict[str, Any]
    case: dict[str, Any]
    frozen_hashes_before: dict[str, str]
    frozen_hashes_after: dict[str, str]


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Q02FailureHarnessRevisionImplementationError(
            f"JSON object required: {path.name}"
        )
    return value


def _hash_frozen_sources() -> dict[str, str]:
    return {
        path.relative_to(PROJECT_ROOT).as_posix(): sha256(
            path.read_bytes()
        ).hexdigest()
        for path in FROZEN_SOURCE_PATHS
    }


def load_q02_failure_harness_revision_implementation() -> dict[str, Any]:
    return _read_json(CONTRACT_PATH)


def validate_q02_failure_harness_revision_implementation(
    contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    value = contract or load_q02_failure_harness_revision_implementation()
    if value.get("status") not in {
        "offline_implementation_pending_formal_validation",
        "offline_implemented_validated_pending_consolidated_audit",
        "offline_implemented_saved_response_and_q01_q10_regression_completed_pending_prompt_boundary_decision",
        "offline_implemented_prompt_guard_completed_pending_real_validation",
    }:
        raise Q02FailureHarnessRevisionImplementationError(
            "unexpected implementation status"
        )
    design = _read_json(DESIGN_PATH)
    if (
        design.get("status")
        != "frozen_by_user_offline_validated_not_implemented"
        or value.get("frozen_design")
        != "config/h3_q02_failure_harness_revision_design.candidate.json"
    ):
        raise Q02FailureHarnessRevisionImplementationError(
            "frozen design prerequisite drifted"
        )
    authorization = value.get("authorization", {})
    if (
        authorization.get("status")
        != "authorized_by_user_for_c1_offline_stages_one_to_three"
        or any(
            authorization.get(field) is not False
            for field in (
                "real_model_calls_allowed",
                "prompt_changes_allowed",
                "h2_changes_allowed",
                "tool_schema_changes_allowed",
                "data_changes_allowed",
                "v2_2_3_resume_allowed",
            )
        )
    ):
        raise Q02FailureHarnessRevisionImplementationError(
            "C1 authorization boundary drifted"
        )
    if any(
        value.get("implemented_boundaries", {}).get(field) is not True
        for field in (
            "separate_non_publishable_rejected_report_evidence",
            "upstream_failure_short_circuit_with_not_evaluated_status",
            "exact_request_reference_plus_controlled_display_alias",
            "outcome_root_cause_before_acceptance_consequences",
        )
    ):
        raise Q02FailureHarnessRevisionImplementationError(
            "implemented boundary drifted"
        )
    expected = value.get("expected_q02", {})
    if (
        expected.get("overall_status") != "failed_stopped"
        or expected.get("root_failure_codes") != ROOT_CODES
        or expected.get("formal_report_is_empty") is not True
        or expected.get("rejected_report_publishable") is not False
        or expected.get("report_completeness_status") != NOT_EVALUATED
        or expected.get("chart_acceptance_status") != NOT_EVALUATED
        or expected.get("diagnostic_manifest")
        != {"total": 27, "covered": 27}
        or expected.get("primary_stop_stage") != "report_validation"
        or expected.get("stop_reason") != "report_validation_failed"
        or expected.get("q02_chart_count_mismatch_present") is not False
    ):
        raise Q02FailureHarnessRevisionImplementationError(
            "expected Q02 state drifted"
        )
    exclusions = value.get("persistent_exclusions", {})
    if any(item is not False for item in exclusions.values()):
        raise Q02FailureHarnessRevisionImplementationError(
            "implementation exclusion or authority drifted"
        )
    if value.get("status") in {
        "offline_implemented_validated_pending_consolidated_audit",
        "offline_implemented_saved_response_and_q01_q10_regression_completed_pending_prompt_boundary_decision",
        "offline_implemented_prompt_guard_completed_pending_real_validation",
    }:
        offline = value.get("offline_validation", {})
        evidence_path = PROJECT_ROOT / str(
            offline.get("evidence_path", "")
        )
        if (
            offline.get("status") != "passed"
            or offline.get("root_failure_codes") != ROOT_CODES
            or offline.get("diagnostic_manifest")
            != {"total": 27, "covered": 27}
            or offline.get("implementation_test_status") != "5_passed"
            or offline.get("full_test_status")
            != "299_passed_49_subtests_passed"
            or offline.get("real_model_called") is not False
            or offline.get("network_used") is not False
            or offline.get("api_key_read") is not False
            or not evidence_path.is_file()
        ):
            raise Q02FailureHarnessRevisionImplementationError(
                "offline implementation evidence drifted"
            )
    return value


def _saved_report_payload() -> dict[str, Any]:
    case = _read_json(SAVED_CASE_PATH)
    content = case["outcome"]["raw_responses"][1]["choices"][0][
        "message"
    ]["content"]
    value = json.loads(content)
    if not isinstance(value, dict):
        raise Q02FailureHarnessRevisionImplementationError(
            "saved Q02 terminal response is not an object"
        )
    return value


class SavedQ02FailureClient(BatchAEvidenceCompleteMockClient):
    def complete_strict_tools(self, **kwargs):
        messages = kwargs["messages"]
        user_question = next(
            item["content"]
            for item in messages
            if item.get("role") == "user"
        )
        payloads = _tool_payloads(messages)
        if (
            user_question == load_frozen_questions()["Q02"]["question"]
            and len(payloads) == 1
        ):
            payload = _saved_report_payload()
            first_fact = payloads[0]["facts"][0]
            payload["report"]["session_id"] = first_fact["session_id"]
            payload["report"]["turn_id"] = first_fact["turn_id"]
            return ChatCompletionResult(
                finish_reason="stop",
                content=json.dumps(payload, ensure_ascii=False),
                tool_calls=(),
                raw_response={
                    "offline": True,
                    "source": "saved_q02_flash_report",
                },
                usage=None,
            )
        return super().complete_strict_tools(**kwargs)


def run_q02_implementation_validation(
    *, output_parent: Path, batch_run_id: str
) -> Q02ImplementationValidationResult:
    validate_q02_failure_harness_revision_implementation()
    before = _hash_frozen_sources()
    transport = OfflineNativeToolTransportV2_1Revision(
        SavedQ02FailureClient(),
        expected_model="deepseek-v4-flash",
        terminal_question_ids=BATCH_A_QUESTION_IDS,
        terminal_json_question_ids=BATCH_A_QUESTION_IDS,
    )
    result = execute_batch_a_validation(
        api_key="offline-q02-formal-implementation-validation-secret",
        registry=FrozenH2MockRegistry(),
        transport=transport,
        authority=validate_offline_execution_request(
            confirmation=BATCH_A_OFFLINE_CONFIRMATION
        ),
        output_parent=output_parent,
        run_id=batch_run_id,
    )
    after = _hash_frozen_sources()
    case = result.cases[0]
    rejected = case["outcome"]["rejected_report_evidence"]
    manifest = case["new_harness_validation"]["evidence_manifest"]
    passed = (
        result.passed is False
        and result.summary["question_ids_executed"] == ["Q02"]
        and result.summary["primary_stop_stage"] == "report_validation"
        and result.summary["primary_stop_codes"] == ROOT_CODES
        and result.summary["stop_reason"] == "report_validation_failed"
        and result.summary["not_evaluated_checks"]
        == ["report_completeness", "chart_acceptance"]
        and case["evaluation_states"]["report_completeness"]
        == NOT_EVALUATED
        and case["evaluation_states"]["chart_acceptance"]
        == NOT_EVALUATED
        and len(manifest) == 27
        and all(item["covered"] for item in manifest)
        and "q02_chart_count_mismatch" not in case["program_failures"]
        and case["outcome"]["report_draft"] is None
        and case["outcome"]["report_validation"] is None
        and rejected["publishable"] is False
        and rejected["charts_materialized"] is False
        and before == after
    )
    return Q02ImplementationValidationResult(
        passed=passed,
        batch_run_id=batch_run_id,
        batch_summary=result.summary,
        case=case,
        frozen_hashes_before=before,
        frozen_hashes_after=after,
    )
