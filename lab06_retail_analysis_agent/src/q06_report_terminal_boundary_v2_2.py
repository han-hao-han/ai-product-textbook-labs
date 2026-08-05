"""Validate the candidate Q06 report terminal boundary V2.2."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = (
    PROJECT_ROOT
    / "config"
    / "h3_q06_report_terminal_boundary_v2_2.candidate.json"
)


class Q06ReportTerminalBoundaryError(ValueError):
    pass


@dataclass(frozen=True)
class Q06ReportTerminalBoundaryPreflight:
    status: str
    model: str
    terminal_tool_choice: str
    tool_visibility: int
    real_model_calls_allowed: bool
    checks: tuple[str, ...]


def load_q06_report_terminal_boundary() -> dict[str, Any]:
    value = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Q06ReportTerminalBoundaryError("contract must be an object")
    return value


def validate_q06_report_terminal_boundary(
    contract: dict[str, Any] | None = None,
) -> Q06ReportTerminalBoundaryPreflight:
    candidate = (
        deepcopy(contract)
        if contract is not None
        else load_q06_report_terminal_boundary()
    )
    checks: list[str] = []
    if candidate.get("status") not in {
        "candidate_pending_offline_validation_and_user_freeze",
        "candidate_offline_validated_pending_user_freeze",
        "frozen_by_user_pending_separate_real_authorization",
    }:
        raise Q06ReportTerminalBoundaryError("unexpected contract status")

    scope = candidate.get("scope", {})
    if (
        scope.get("question_ids") != ["Q06"]
        or scope.get("model") != "deepseek-v4-flash"
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
        raise Q06ReportTerminalBoundaryError("scope drifted")
    checks.append("q06_flash_only_without_frozen_input_changes")

    protocol = candidate.get("redesigned_protocol", {})
    if (
        protocol.get("response_1", {}).get("tool_choice") != "auto"
        or protocol.get("response_2", {}).get("tool_choice") != "auto"
        or protocol.get("response_3", {}).get("tool_choice") != "none"
        or any(
            protocol.get(key, {}).get("tool_visibility") != 7
            for key in ("response_1", "response_2", "response_3")
        )
        or protocol.get("response_3", {}).get("response_format_added")
        is not False
        or protocol.get("terminal_trigger", {}).get(
            "executed_tool_sequence"
        )
        != ["analyze_time_trend", "rank_products"]
        or protocol.get("terminal_trigger", {}).get(
            "program_may_synthesize_tool_or_arguments"
        )
        is not False
    ):
        raise Q06ReportTerminalBoundaryError("terminal protocol drifted")
    checks.append("auto_auto_none_with_all_seven_tools_visible")

    roles = candidate.get("mainline_compatibility", {})
    required_true = (
        "model_selects_business_tools",
        "model_generates_business_tool_arguments",
        "pandas_performs_all_business_calculation",
        "program_controls_tool_permission_state",
        "model_organizes_report",
        "program_validates_fact_trace",
    )
    if any(roles.get(field) is not True for field in required_true) or any(
        roles.get(field) is not False
        for field in (
            "program_preselects_business_tool",
            "program_generates_report_numbers",
        )
    ):
        raise Q06ReportTerminalBoundaryError("mainline roles drifted")
    checks.append("model_tool_program_and_report_roles_preserved")

    offline = candidate.get("offline_validation", {})
    if any(
        offline.get(field) is not False
        for field in (
            "real_network_opened",
            "api_key_read",
            "real_model_called",
        )
    ):
        raise Q06ReportTerminalBoundaryError("offline boundary drifted")
    if candidate.get("status") in {
        "candidate_offline_validated_pending_user_freeze",
        "frozen_by_user_pending_separate_real_authorization",
    } and (
        offline.get("status") != "passed"
        or offline.get("legacy_tool_choices")
        != ["auto", "auto", "auto"]
        or offline.get("redesigned_tool_choices")
        != ["auto", "auto", "none"]
        or offline.get("redesigned_report_validation_status") != "passed"
        or offline.get("redesigned_chart_count") != 2
    ):
        raise Q06ReportTerminalBoundaryError(
            "offline validation evidence drifted"
        )
    authorization = candidate.get("authorization", {})
    if (
        authorization.get("real_model_calls_allowed") is not False
        or authorization.get("new_exact_user_authorization_required")
        is not True
        or authorization.get("prior_flash_authorization_reusable")
        is not False
    ):
        raise Q06ReportTerminalBoundaryError("authorization drifted")
    checks.append("offline_only_and_prior_authorization_not_reusable")

    return Q06ReportTerminalBoundaryPreflight(
        status="passed",
        model="deepseek-v4-flash",
        terminal_tool_choice="none",
        tool_visibility=7,
        real_model_calls_allowed=False,
        checks=tuple(checks),
    )
