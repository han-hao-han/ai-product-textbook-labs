"""Offline design guard for one bounded Q06 report revision."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.agent_protocol import FinalReportResponse, parse_control_response
from src.fact_schema import FactRecord
from src.report_validation import ReportValidationResult, validate_report


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = (
    PROJECT_ROOT
    / "config"
    / "h3_q06_report_revision_feedback_boundary_v2_2_3.candidate.json"
)
V2_2_2_CONTRACT_PATH = (
    PROJECT_ROOT
    / "config"
    / "h3_report_evidence_semantic_boundary_v2_2_2.candidate.json"
)
REAL_EVIDENCE_PATH = (
    PROJECT_ROOT
    / "results"
    / "raw"
    / "q06_v2_2_1_flash_real_revalidation_20260803T153719_794668+0800"
    / "Q06.json"
)
EXPECTED_REPAIRABLE_CODES = {
    "untraceable_numeric_token",
    "model_supplied_fact_citation",
    "duplicate_claim_reference",
    "unknown_fact",
    "fact_value_mismatch",
    "fact_display_value_mismatch",
    "fact_unit_mismatch",
    "fact_rank_mismatch",
    "fact_period_mismatch",
    "fact_start_date_mismatch",
    "fact_end_date_mismatch",
    "unsupported_significance_claim",
    "unsupported_average_value_claim",
    "unsupported_product_classification",
    "unsupported_quantity_superlative",
    "unsupported_order_superlative",
}
EXPECTED_HARD_STOP_CODES = {"duplicate_fact_id", "cross_turn_fact"}


class Q06ReportRevisionFeedbackBoundaryError(ValueError):
    """Raised when the V2.2.3 offline boundary drifts."""


class StrictFeedbackModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ReportRevisionFeedbackIssue(StrictFeedbackModel):
    code: str = Field(min_length=1, max_length=100)
    location: str = Field(min_length=1, max_length=200)
    unsupported_expression: str = Field(min_length=1, max_length=200)
    allowed_action: str = Field(min_length=1, max_length=200)


class ReportRevisionFeedbackPayload(StrictFeedbackModel):
    schema_version: Literal[
        "1.5.6-h3-q06-report-validation-feedback-v2.2.3-v1"
    ]
    feedback_type: Literal["report_validation_feedback"]
    question_id: Literal["Q06"]
    source_report_response_index: Literal[3]
    revision_attempt: Literal[1]
    maximum_report_revision_responses: Literal[1]
    instruction: str = Field(min_length=1, max_length=1000)
    issues: list[ReportRevisionFeedbackIssue] = Field(
        min_length=1,
        max_length=24,
    )


@dataclass(frozen=True)
class SavedQ06FeedbackReplay:
    source_sha256: str
    source_response_unchanged: bool
    formal_validation_status: str
    formal_issue_count: int
    manual_review_flag_count: int
    fact_count: int
    feedback: ReportRevisionFeedbackPayload
    feedback_sha256: str


def load_q06_report_revision_feedback_contract() -> dict[str, Any]:
    value = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Q06ReportRevisionFeedbackBoundaryError(
            "V2.2.3 contract must be a JSON object"
        )
    return value


def validate_q06_report_revision_feedback_contract(
    contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    value = contract or load_q06_report_revision_feedback_contract()
    v2_2_2 = json.loads(V2_2_2_CONTRACT_PATH.read_text(encoding="utf-8"))
    if value.get("status") not in {
        "offline_design_pending_validation_and_user_freeze",
        "offline_validated_pending_user_freeze",
        "paused_by_user_pending_q01_q10_acceptance_harness_audit",
    }:
        raise Q06ReportRevisionFeedbackBoundaryError(
            "unexpected V2.2.3 status"
        )
    prerequisite = value.get("prerequisite", {})
    if (
        prerequisite.get("v2_2_2_status")
        != "frozen_by_user_formal_validator_integrated_offline_validated"
        or v2_2_2.get("status") != prerequisite.get("v2_2_2_status")
        or prerequisite.get("source_response_index") != 3
        or prerequisite.get("source_formal_issue_count") != 8
    ):
        raise Q06ReportRevisionFeedbackBoundaryError(
            "V2.2.3 prerequisite drifted"
        )
    scope = value.get("scope", {})
    if (
        scope.get("question_ids") != ["Q06"]
        or scope.get("offline_design_only") is not True
        or scope.get("real_model_calls_allowed") is not False
        or scope.get("api_key_may_be_read") is not False
        or any(
            scope.get(field) is not False
            for field in (
                "current_prompt_changed",
                "current_model_control_schema_changed",
                "fact_schema_or_values_changed",
                "seven_tool_whitelist_changed",
                "h2_data_or_metrics_changed",
                "formal_validator_changed",
                "orchestrator_changed",
            )
        )
    ):
        raise Q06ReportRevisionFeedbackBoundaryError(
            "V2.2.3 scope or authority drifted"
        )
    feedback = value.get("deterministic_feedback_candidate", {})
    action_map = feedback.get("repairable_issue_action_map", {})
    if (
        set(action_map) != EXPECTED_REPAIRABLE_CODES
        or set(feedback.get("hard_stop_issue_codes", []))
        != EXPECTED_HARD_STOP_CODES
        or feedback.get("manual_review_flags_are_not_deterministic_failures")
        is not True
        or "manual_review_flags" not in feedback.get("exclude_fields", [])
        or "candidate_fact_ids_selected_by_program"
        not in feedback.get("exclude_fields", [])
        or "program_generated_replacement_statement"
        not in feedback.get("exclude_fields", [])
    ):
        raise Q06ReportRevisionFeedbackBoundaryError(
            "V2.2.3 feedback whitelist or exclusion drifted"
        )
    protocol = value.get("candidate_revision_protocol", {})
    if (
        protocol.get("active") is not False
        or protocol.get("maximum_report_revision_responses") != 1
        or protocol.get("maximum_total_model_responses_if_future_authorized")
        != 4
        or protocol.get("automatic_retry_count") != 0
        or protocol.get("tool_choice") != "none"
        or protocol.get("response_format") != {"type": "json_object"}
        or protocol.get("tool_calls_allowed_in_revision_response") is not False
        or protocol.get("same_final_report_response_schema") is not True
        or protocol.get("current_three_response_real_plan_remains_unchanged")
        is not True
        or protocol.get("separate_plan_freeze_and_real_call_authorization_required")
        is not True
    ):
        raise Q06ReportRevisionFeedbackBoundaryError(
            "V2.2.3 revision protocol drifted"
        )
    acceptance = value.get("revision_acceptance_candidate", {})
    if (
        acceptance.get("formal_report_validation_must_pass_from_scratch")
        is not True
        or acceptance.get("chart_requests_must_equal_initial_report")
        is not True
        or acceptance.get("failure_after_one_revision_stops_and_saves_both_responses")
        is not True
        or acceptance.get("program_may_not_auto_repair_after_failure")
        is not True
    ):
        raise Q06ReportRevisionFeedbackBoundaryError(
            "V2.2.3 acceptance boundary drifted"
        )
    authorization = value.get("authorization", {})
    if (
        authorization.get("candidate_is_not_frozen") is not True
        or authorization.get("real_model_calls_allowed") is not False
        or authorization.get("current_v2_2_1_authorization_consumed")
        is not True
    ):
        raise Q06ReportRevisionFeedbackBoundaryError(
            "V2.2.3 authorization drifted"
        )
    if value.get("status") in {
        "offline_validated_pending_user_freeze",
        "paused_by_user_pending_q01_q10_acceptance_harness_audit",
    }:
        offline = value.get("offline_validation", {})
        mock_regression = offline.get("q01_q10_mock_regression", {})
        if (
            offline.get("status") != "passed"
            or offline.get("source_response_unchanged") is not True
            or offline.get("formal_issue_count") != 8
            or offline.get("manual_review_flags_excluded") != 8
            or offline.get("feedback_issue_count") != 8
            or offline.get("fact_count_unchanged") != 48
            or offline.get("negative_probes_passed") != 9
            or offline.get("full_tests")
            != "233_passed_29_subtests_passed"
            or mock_regression.get("status") != "passed"
            or mock_regression.get("questions_passed") != 10
            or mock_regression.get("questions_total") != 10
            or mock_regression.get("real_model_called") is not False
            or mock_regression.get("network_used") is not False
            or offline.get("candidate_result")
            != "feedback_ready_revision_not_executed"
            or offline.get("real_model_called") is not False
            or offline.get("api_key_read") is not False
        ):
            raise Q06ReportRevisionFeedbackBoundaryError(
                "V2.2.3 offline validation evidence drifted"
            )
    if value.get("status") == (
        "paused_by_user_pending_q01_q10_acceptance_harness_audit"
    ):
        pause = value.get("user_pause", {})
        if (
            pause.get("status") != "paused_by_user"
            or pause.get("candidate_revision_protocol_remains_inactive")
            is not True
            or pause.get("current_prompt_remains_unchanged") is not True
            or pause.get("orchestrator_remains_unchanged") is not True
            or pause.get("real_model_calls_allowed") is not False
        ):
            raise Q06ReportRevisionFeedbackBoundaryError(
                "V2.2.3 pause boundary drifted"
            )
    return value


def _unsupported_expression(code: str, message: str) -> str:
    if code == "untraceable_numeric_token":
        match = re.search(r"：([^。]+)。?$", message)
    else:
        match = re.search(r"触发表达：([^。]+)。?$", message)
    if match is not None:
        return match.group(1)
    return code


def build_report_revision_feedback(
    validation: ReportValidationResult,
    *,
    contract: dict[str, Any] | None = None,
) -> ReportRevisionFeedbackPayload:
    value = validate_q06_report_revision_feedback_contract(contract)
    if validation.status != "failed" or not validation.issues:
        raise Q06ReportRevisionFeedbackBoundaryError(
            "feedback requires a failed deterministic report validation"
        )
    action_map = value["deterministic_feedback_candidate"][
        "repairable_issue_action_map"
    ]
    codes = {issue.code for issue in validation.issues}
    hard_stops = codes & EXPECTED_HARD_STOP_CODES
    unsupported = codes - set(action_map)
    if hard_stops or unsupported:
        raise Q06ReportRevisionFeedbackBoundaryError(
            "hard-stop or non-whitelisted issue cannot enter revision feedback"
        )
    issues = [
        ReportRevisionFeedbackIssue(
            code=issue.code,
            location=issue.location,
            unsupported_expression=_unsupported_expression(
                issue.code,
                issue.message,
            ),
            allowed_action=action_map[issue.code],
        )
        for issue in validation.issues
    ]
    return ReportRevisionFeedbackPayload(
        schema_version=(
            "1.5.6-h3-q06-report-validation-feedback-v2.2.3-v1"
        ),
        feedback_type="report_validation_feedback",
        question_id="Q06",
        source_report_response_index=3,
        revision_attempt=1,
        maximum_report_revision_responses=1,
        instruction=(
            "只重写完整报告；不得调用工具、修改工具结果或FACT、"
            "计算新指标、使用其他claim的证据或改变图表请求。"
        ),
        issues=issues,
    )


def replay_saved_q06_feedback_design(
    evidence_path: Path = REAL_EVIDENCE_PATH,
) -> SavedQ06FeedbackReplay:
    source_bytes = evidence_path.read_bytes()
    source_hash = sha256(source_bytes).hexdigest()
    payload = json.loads(source_bytes.decode("utf-8"))
    raw_responses = payload["outcome"]["raw_responses"]
    content = raw_responses[2]["choices"][0]["message"]["content"]
    control = parse_control_response(content)
    if not isinstance(control, FinalReportResponse):
        raise Q06ReportRevisionFeedbackBoundaryError(
            "saved Q06 terminal response is not a report"
        )
    facts = [
        FactRecord.model_validate(item)
        for item in payload["outcome"]["facts"]
    ]
    validation = validate_report(control.report, facts)
    feedback = build_report_revision_feedback(validation)
    feedback_json = feedback.model_dump_json()
    return SavedQ06FeedbackReplay(
        source_sha256=source_hash,
        source_response_unchanged=(
            sha256(evidence_path.read_bytes()).hexdigest() == source_hash
        ),
        formal_validation_status=validation.status,
        formal_issue_count=len(validation.issues),
        manual_review_flag_count=len(validation.manual_review_flags),
        fact_count=len(facts),
        feedback=feedback,
        feedback_sha256=sha256(feedback_json.encode("utf-8")).hexdigest(),
    )
