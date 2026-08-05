"""Offline validator for the native report Prompt evidence-guard design."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = (
    PROJECT_ROOT
    / "config"
    / "h3_native_report_prompt_evidence_guard_design.candidate.json"
)
EXPECTED_ROOT_CODES = [
    "untraceable_numeric_token",
    "unsupported_average_value_claim",
    "unsupported_average_value_claim",
]
FORBIDDEN_HARDCODING = (
    "Q02",
    "524878",
    "206248.77",
    "DOTCOM POSTAGE",
    "PAPER CRAFT",
)


class NativeReportPromptEvidenceGuardDesignError(ValueError):
    """Raised when the candidate design widens scope or loses evidence."""


@dataclass(frozen=True)
class NativeReportPromptEvidenceGuardDesignResult:
    passed: bool
    targeted_root_issue_count: int
    root_issue_count: int
    rule_ids: tuple[str, ...]
    active_prompt_sha256: str
    saved_response_sha256: str
    q01_q10_offline_status: str
    negative_probes: dict[str, bool]


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise NativeReportPromptEvidenceGuardDesignError(
            f"JSON object required: {path.name}"
        )
    return value


def load_native_report_prompt_evidence_guard_design() -> dict[str, Any]:
    return _read_json(CONTRACT_PATH)


def _hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def validate_native_report_prompt_evidence_guard_design(
    contract: dict[str, Any] | None = None,
) -> NativeReportPromptEvidenceGuardDesignResult:
    value = contract or load_native_report_prompt_evidence_guard_design()
    if value.get("status") not in {
        "candidate_pending_offline_validation_and_user_freeze",
        "candidate_offline_validated_pending_user_freeze_and_implementation_authorization",
        "frozen_by_user_offline_validated_implementation_authorized",
    }:
        raise NativeReportPromptEvidenceGuardDesignError(
            "unexpected candidate status"
        )

    source = value.get("source_evidence", {})
    active_prompt_path = PROJECT_ROOT / str(source.get("active_report_prompt"))
    saved_q02_path = PROJECT_ROOT / str(source.get("saved_q02_path"))
    c1_audit_path = PROJECT_ROOT / str(source.get("c1_audit_path"))
    active_prompt_hash = _hash(active_prompt_path)
    saved_response_hash = _hash(saved_q02_path)
    if (
        active_prompt_hash != source.get("active_report_prompt_sha256")
        or source.get("tool_reference_answer_status") != "passed"
        or source.get("report_status") != "failed"
        or source.get("root_failure_codes") != EXPECTED_ROOT_CODES
    ):
        raise NativeReportPromptEvidenceGuardDesignError(
            "source evidence or active Prompt drifted"
        )

    scope = value.get("scope", {})
    false_scope_fields = (
        "modify_frozen_prompt_in_place",
        "modify_agent_system_prompt",
        "modify_h2",
        "modify_data",
        "modify_tool_schema",
        "modify_report_schema",
        "modify_fact_schema_or_values",
        "modify_acceptance_root_rules",
        "resume_v2_2_3",
        "add_report_repair_or_retry",
        "real_model_calls_allowed",
    )
    if (
        scope.get("target") != "active_native_tool_report_prompt_only"
        or any(scope.get(field) is not False for field in false_scope_fields)
        or scope.get("proposed_new_prompt_path")
        == source.get("active_report_prompt")
    ):
        raise NativeReportPromptEvidenceGuardDesignError(
            "candidate scope widened or frozen Prompt would be overwritten"
        )

    rules = value.get("candidate_additive_rules", [])
    if [rule.get("rule_id") for rule in rules] != [
        "PROMPT-EVIDENCE-01",
        "PROMPT-EVIDENCE-02",
        "PROMPT-EVIDENCE-03",
    ]:
        raise NativeReportPromptEvidenceGuardDesignError(
            "candidate additive rule set drifted"
        )
    combined_text = "\n".join(str(rule.get("text", "")) for rule in rules)
    if any(token in combined_text for token in FORBIDDEN_HARDCODING):
        raise NativeReportPromptEvidenceGuardDesignError(
            "candidate contains Q02-specific hardcoding"
        )
    if not all(
        token in combined_text
        for token in (
            "同一条claim",
            "当前轮FACT",
            "average_order_value",
            "unit_price",
            "不得组合多个FACT",
            "当前FACT无法判断",
        )
    ):
        raise NativeReportPromptEvidenceGuardDesignError(
            "candidate does not express the three evidence guards"
        )

    targeted_codes = {
        code
        for rule in rules
        for code in rule.get("targets_issue_codes", [])
    }
    if targeted_codes != set(EXPECTED_ROOT_CODES):
        raise NativeReportPromptEvidenceGuardDesignError(
            "candidate does not target every saved root issue class"
        )

    c1_audit = _read_json(c1_audit_path)
    if (
        c1_audit.get("status") != "passed"
        or c1_audit.get("q01_q10", {}).get("status") != "passed"
        or c1_audit.get("real_model_called") is not False
        or c1_audit.get("network_used") is not False
        or c1_audit.get("v2_2_3_resumed") is not False
    ):
        raise NativeReportPromptEvidenceGuardDesignError(
            "C1 offline prerequisite evidence drifted"
        )

    decision = value.get("decision_required", {})
    if not all(
        decision.get(field) is True
        for field in (
            "user_freeze_required",
            "separate_implementation_authorization_required",
            "separate_real_validation_authorization_required",
            "freeze_does_not_authorize_implementation",
            "freeze_does_not_authorize_real_calls",
        )
    ):
        raise NativeReportPromptEvidenceGuardDesignError(
            "user decision boundary is incomplete"
        )
    if value.get("status") == (
        "frozen_by_user_offline_validated_implementation_authorized"
    ):
        authority = value.get(
            "user_freeze_and_implementation_authorization", {}
        )
        if (
            authority.get("status") != "frozen_and_authorized_by_user"
            or any(
                authority.get(field) is not False
                for field in (
                    "real_model_calls_allowed",
                    "h2_changes_allowed",
                    "data_changes_allowed",
                    "tool_report_fact_schema_changes_allowed",
                    "acceptance_root_rule_changes_allowed",
                    "v2_2_3_resume_allowed",
                )
            )
        ):
            raise NativeReportPromptEvidenceGuardDesignError(
                "frozen implementation authority drifted"
            )
    if value.get("status") == (
        "candidate_offline_validated_pending_user_freeze_and_implementation_authorization"
    ):
        offline = value.get("offline_validation", {})
        evidence_path = PROJECT_ROOT / str(
            offline.get("evidence_path", "")
        )
        if (
            offline.get("status") != "passed"
            or offline.get("targeted_root_issue_count") != 3
            or offline.get("root_issue_count") != 3
            or offline.get("negative_probes_passed") != 7
            or offline.get("negative_probes_total") != 7
            or offline.get("active_prompt_unchanged") is not True
            or offline.get("saved_q02_response_unchanged") is not True
            or offline.get("q01_q10_offline_status") != "passed"
            or any(
                offline.get(field) is not False
                for field in (
                    "prompt_changed",
                    "validator_changed",
                    "real_model_called",
                    "network_used",
                    "api_key_read",
                    "v2_2_3_resumed",
                )
            )
            or not evidence_path.is_file()
        ):
            raise NativeReportPromptEvidenceGuardDesignError(
                "formal offline design evidence drifted"
            )

    negative_probes = {
        "active_prompt_unchanged": (
            active_prompt_hash == source["active_report_prompt_sha256"]
        ),
        "no_q02_hardcoding": not any(
            token in combined_text for token in FORBIDDEN_HARDCODING
        ),
        "no_in_place_prompt_edit": not scope[
            "modify_frozen_prompt_in_place"
        ],
        "no_validator_change": not scope[
            "modify_acceptance_root_rules"
        ],
        "no_v2_2_3_resume": not scope["resume_v2_2_3"],
        "no_report_retry": not scope["add_report_repair_or_retry"],
        "no_real_call": not scope["real_model_calls_allowed"],
    }
    return NativeReportPromptEvidenceGuardDesignResult(
        passed=all(negative_probes.values()),
        targeted_root_issue_count=len(EXPECTED_ROOT_CODES),
        root_issue_count=len(EXPECTED_ROOT_CODES),
        rule_ids=tuple(rule["rule_id"] for rule in rules),
        active_prompt_sha256=active_prompt_hash,
        saved_response_sha256=saved_response_hash,
        q01_q10_offline_status=c1_audit["q01_q10"]["status"],
        negative_probes=negative_probes,
    )
