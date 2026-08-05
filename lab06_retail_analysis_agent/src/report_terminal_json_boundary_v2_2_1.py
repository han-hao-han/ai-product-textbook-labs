"""Offline contract checks for the V2.2.1 terminal JSON candidate."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = (
    PROJECT_ROOT
    / "config"
    / "h3_report_terminal_json_boundary_v2_2_1.candidate.json"
)
COVERAGE_PATH = (
    PROJECT_ROOT
    / "config"
    / "h3_q01_q10_validation_coverage_v2_2_1.json"
)


class ReportTerminalJsonBoundaryError(ValueError):
    """Raised when the offline candidate exceeds the reopened boundary."""


@dataclass(frozen=True)
class ReportTerminalJsonBoundaryPreflight:
    model: str
    question_ids: tuple[str, ...]
    tool_choice_sequence: tuple[str, ...]
    response_formats: tuple[dict[str, str] | None, ...]
    tool_visibility: tuple[int, ...]
    dsml_extraction_allowed: bool
    real_model_calls_allowed: bool


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ReportTerminalJsonBoundaryError(
            f"contract must be a JSON object: {path.name}"
        )
    return payload


def load_report_terminal_json_boundary() -> dict[str, Any]:
    return _load(CONTRACT_PATH)


def load_q01_q10_validation_coverage() -> dict[str, Any]:
    return _load(COVERAGE_PATH)


def validate_report_terminal_json_boundary(
    payload: dict[str, Any] | None = None,
) -> ReportTerminalJsonBoundaryPreflight:
    contract = payload or load_report_terminal_json_boundary()
    scope = contract.get("scope", {})
    protocol = contract.get("candidate_protocol", {})
    response_1 = protocol.get("response_1", {})
    response_2 = protocol.get("response_2", {})
    response_3 = protocol.get("response_3", {})
    trigger = protocol.get("terminal_trigger", {})
    fail_closed = contract.get("fail_closed_rules", {})
    authorization = contract.get("authorization", {})

    if contract.get("status") != (
        "frozen_by_user_pending_separate_real_authorization"
    ):
        raise ReportTerminalJsonBoundaryError(
            "V2.2.1 frozen status is missing"
        )
    if scope.get("question_ids") != ["Q06"]:
        raise ReportTerminalJsonBoundaryError(
            "V2.2.1 may only reopen Q06 serialization"
        )
    immutable_false = (
        "prompt_changed",
        "control_schema_changed",
        "data_changed",
        "acceptance_rules_changed",
        "seven_tool_whitelist_changed",
        "h2_metrics_changed",
        "real_model_calls_allowed",
    )
    if any(scope.get(key) is not False for key in immutable_false):
        raise ReportTerminalJsonBoundaryError(
            "V2.2.1 changed a frozen boundary or enabled real calls"
        )
    if [
        response_1.get("tool_choice"),
        response_2.get("tool_choice"),
        response_3.get("tool_choice"),
    ] != ["auto", "auto", "none"]:
        raise ReportTerminalJsonBoundaryError(
            "tool_choice sequence must remain auto/auto/none"
        )
    response_formats = (
        response_1.get("response_format"),
        response_2.get("response_format"),
        response_3.get("response_format"),
    )
    if response_formats != (None, None, {"type": "json_object"}):
        raise ReportTerminalJsonBoundaryError(
            "only the third response may enable json_object"
        )
    if [
        response_1.get("tool_visibility"),
        response_2.get("tool_visibility"),
        response_3.get("tool_visibility"),
    ] != [7, 7, 7]:
        raise ReportTerminalJsonBoundaryError(
            "all three responses must retain seven-tool visibility"
        )
    if trigger.get("executed_tool_sequence") != [
        "analyze_time_trend",
        "rank_products",
    ]:
        raise ReportTerminalJsonBoundaryError(
            "Q06 evidence trigger was changed"
        )
    if trigger.get("program_may_synthesize_business_tool_or_arguments"):
        raise ReportTerminalJsonBoundaryError(
            "program-generated business tool plans are forbidden"
        )
    required_fail_closed = {
        "dsml_extraction_allowed": False,
        "pseudo_tool_call_repair_allowed": False,
        "schema_repair_allowed": False,
        "empty_content_is_failure": True,
        "truncated_json_is_failure": True,
        "valid_json_wrong_schema_is_failure": True,
        "automatic_retry_count": 0,
    }
    if any(
        fail_closed.get(key) != value
        for key, value in required_fail_closed.items()
    ):
        raise ReportTerminalJsonBoundaryError(
            "fail-closed serialization rules were weakened"
        )
    if authorization.get("real_model_calls_allowed") is not False:
        raise ReportTerminalJsonBoundaryError(
            "V2.2.1 has no real-model authorization"
        )
    freeze = contract.get("user_freeze", {})
    if (
        freeze.get("status") != "frozen_by_user"
        or freeze.get("freeze_does_not_authorize_real_calls") is not True
        or freeze.get("other_q01_q10_cases_not_in_scope") is not True
    ):
        raise ReportTerminalJsonBoundaryError(
            "V2.2.1 user-freeze boundary is incomplete"
        )
    return ReportTerminalJsonBoundaryPreflight(
        model=str(scope.get("model")),
        question_ids=tuple(scope["question_ids"]),
        tool_choice_sequence=("auto", "auto", "none"),
        response_formats=response_formats,
        tool_visibility=(7, 7, 7),
        dsml_extraction_allowed=False,
        real_model_calls_allowed=False,
    )


def validate_q01_q10_validation_coverage(
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    coverage = payload or load_q01_q10_validation_coverage()
    questions = coverage.get("questions", [])
    ids = [item.get("question_id") for item in questions]
    expected = [f"Q{index:02d}" for index in range(1, 11)]
    if ids != expected:
        raise ReportTerminalJsonBoundaryError(
            "coverage matrix must contain Q01-Q10 exactly once and in order"
        )
    if any(
        item.get("offline_mock") != "passed"
        or item.get("offline_transport") != "passed"
        for item in questions
    ):
        raise ReportTerminalJsonBoundaryError(
            "coverage matrix conflicts with frozen offline evidence"
        )
    by_id = {item["question_id"]: item for item in questions}
    if by_id["Q06"].get("current_native_flash_real") != "failed":
        raise ReportTerminalJsonBoundaryError(
            "coverage matrix must preserve the Q06 real failure"
        )
    if any(
        by_id[question_id].get("current_native_flash_real") != "not_run"
        for question_id in expected
        if question_id != "Q06"
    ):
        raise ReportTerminalJsonBoundaryError(
            "unrun current Flash cases must not be marked validated"
        )
    if coverage.get("authorization", {}).get(
        "real_model_calls_allowed"
    ) is not False:
        raise ReportTerminalJsonBoundaryError(
            "coverage audit must not authorize real calls"
        )
    return coverage
