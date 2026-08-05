"""Consolidated, read-only audit for the user-authorized C1 offline stages."""

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
    / "h3_c1_q02_q01_q10_offline_consolidated_audit.json"
)
ROOT_CODES = [
    "untraceable_numeric_token",
    "unsupported_average_value_claim",
    "unsupported_average_value_claim",
]
NOT_EVALUATED = (
    "not_evaluated_due_to_upstream_report_validation_failure"
)


class C1OfflineConsolidatedAuditError(ValueError):
    """Raised when an authorized boundary or evidence chain has drifted."""


@dataclass(frozen=True)
class C1OfflineConsolidatedAuditResult:
    passed: bool
    q02_summary: dict[str, Any]
    q01_q10_summary: dict[str, Any]
    batch_a_summary: dict[str, Any]
    frozen_hashes: dict[str, str]
    findings: tuple[dict[str, str], ...]


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise C1OfflineConsolidatedAuditError(
            f"JSON object required: {path.name}"
        )
    return value


def load_c1_offline_consolidated_audit_contract() -> dict[str, Any]:
    return _read_json(CONTRACT_PATH)


def _validate_authority(contract: dict[str, Any]) -> None:
    if contract.get("status") not in {
        "offline_audit_pending_formal_validation",
        "offline_audit_completed_pending_user_checkpoint",
    }:
        raise C1OfflineConsolidatedAuditError(
            "unexpected consolidated audit status"
        )
    authorization = contract.get("authorization", {})
    if authorization.get("status") != (
        "authorized_by_user_for_c1_offline_stages_one_to_three"
    ):
        raise C1OfflineConsolidatedAuditError(
            "C1 authorization status drifted"
        )
    if any(
        value is not False
        for key, value in authorization.items()
        if key != "status"
    ):
        raise C1OfflineConsolidatedAuditError(
            "C1 mutation or real-call authority widened"
        )
    exclusions = contract.get("persistent_exclusions", {})
    if not exclusions or any(value is not False for value in exclusions.values()):
        raise C1OfflineConsolidatedAuditError(
            "C1 persistent exclusion drifted"
        )
    if contract.get("status") == (
        "offline_audit_completed_pending_user_checkpoint"
    ):
        offline = contract.get("offline_validation", {})
        evidence_path = PROJECT_ROOT / str(
            offline.get("evidence_path", "")
        )
        if (
            offline.get("status") != "passed"
            or offline.get("targeted_test_status") != "4_passed"
            or offline.get("q01_q10_full_harness_regression")
            != "passed_10_of_10"
            or offline.get("q01_q10_negative_probes")
            != "9_passed_of_9"
            or offline.get("frozen_source_hashes_matched") is not True
            or offline.get("active_native_tool_prompt_hashes_included")
            is not True
            or any(
                offline.get(field) is not False
                for field in (
                    "real_model_called",
                    "network_used",
                    "api_key_read",
                    "v2_2_3_resumed",
                )
            )
            or not evidence_path.is_file()
        ):
            raise C1OfflineConsolidatedAuditError(
                "formal consolidated audit evidence drifted"
            )


def _verify_frozen_hashes(contract: dict[str, Any]) -> dict[str, str]:
    expected = contract.get("frozen_source_hashes", {})
    observed = {
        relative_path: sha256(
            (PROJECT_ROOT / relative_path).read_bytes()
        ).hexdigest()
        for relative_path in expected
    }
    if observed != expected:
        raise C1OfflineConsolidatedAuditError(
            "one or more frozen H2, active Prompt, tool Schema, or V2.2.3 sources drifted"
        )
    return observed


def _evidence(contract: dict[str, Any], key: str) -> dict[str, Any]:
    relative_path = contract.get("evidence", {}).get(key)
    if not isinstance(relative_path, str):
        raise C1OfflineConsolidatedAuditError(
            f"missing evidence path: {key}"
        )
    path = PROJECT_ROOT / relative_path
    if not path.is_file():
        raise C1OfflineConsolidatedAuditError(
            f"missing evidence file: {relative_path}"
        )
    return _read_json(path)


def _validate_q02(summary: dict[str, Any]) -> None:
    if (
        summary.get("status") != "passed"
        or summary.get("q02_status") != "failed_stopped"
        or summary.get("root_failure_codes") != ROOT_CODES
        or summary.get("root_failure_codes_unchanged") is not True
        or summary.get("formal_report_is_empty") is not True
        or summary.get("rejected_report_publishable") is not False
        or summary.get("report_completeness_status") != NOT_EVALUATED
        or summary.get("chart_acceptance_status") != NOT_EVALUATED
        or summary.get("diagnostic_manifest")
        != {"total": 27, "covered": 27}
        or summary.get("primary_stop_stage") != "report_validation"
        or summary.get("stop_reason") != "report_validation_failed"
        or summary.get("q02_chart_count_mismatch_present") is not False
        or summary.get("frozen_sources_unchanged") is not True
    ):
        raise C1OfflineConsolidatedAuditError(
            "Q02 saved-response evidence does not satisfy the frozen design"
        )


def _validate_q01_q10(summary: dict[str, Any]) -> None:
    verification = summary.get("verification", {})
    expected_question_ids = [f"Q{index:02d}" for index in range(1, 11)]
    if (
        summary.get("status") != "passed"
        or sorted(verification.get("generic_mock_statuses", {}))
        != expected_question_ids
        or verification.get("manifest_all_covered") is not True
        or verification.get("current_non_selected_metric_rank_counts")
        != {"Q02": 0, "Q03": 0, "Q06": 0}
        or summary.get("negative_probe_passed") != 9
        or summary.get("negative_probe_total") != 9
        or verification.get("source_files_unchanged_during_verification")
        is not True
    ):
        raise C1OfflineConsolidatedAuditError(
            "Q01-Q10 full Harness regression evidence drifted"
        )


def _validate_batch_a(summary: dict[str, Any]) -> None:
    success = summary.get("success_scenario", {})
    network_failure = summary.get("network_failure_scenario", {})
    semantic_failure = summary.get("semantic_failure_scenario", {})
    safety = summary.get("evidence_safety", {})
    if (
        summary.get("status") != "passed"
        or summary.get("authorization_gate", {}).get("blocked") is not True
        or summary.get("authorization_gate", {}).get("api_key_read") is not False
        or success.get("status")
        != "passed_deterministic_pending_manual_review"
        or success.get("actual_response_attempts") != 8
        or success.get("response_attempt_upper_bound") != 8
        or network_failure.get("status") != "failed_stopped"
        or semantic_failure.get("status") != "failed_stopped"
        or network_failure.get("question_ids_not_executed")
        != ["Q08", "Q09", "Q10"]
        or semantic_failure.get("question_ids_not_executed")
        != ["Q08", "Q09", "Q10"]
        or summary.get("ninth_attempt_probe", {}).get(
            "ninth_attempt_blocked"
        )
        is not True
        or safety.get("success_evidence_safe") is not True
        or safety.get("failure_evidence_safe") is not True
    ):
        raise C1OfflineConsolidatedAuditError(
            "Batch A offline safety evidence drifted"
        )


def _verify_no_real_activity(*summaries: dict[str, Any]) -> None:
    forbidden_true_fields = (
        "real_model_called",
        "network_used",
        "real_network_opened",
        "api_key_read",
        "api_key_read_from_environment",
        "v2_2_3_resumed",
    )
    for summary in summaries:
        if any(summary.get(field) is True for field in forbidden_true_fields):
            raise C1OfflineConsolidatedAuditError(
                "offline audit evidence reports forbidden real activity"
            )


def run_c1_offline_consolidated_audit(
    contract: dict[str, Any] | None = None,
) -> C1OfflineConsolidatedAuditResult:
    value = contract or load_c1_offline_consolidated_audit_contract()
    _validate_authority(value)
    frozen_hashes = _verify_frozen_hashes(value)
    q02 = _evidence(value, "q02_saved_response_regression")
    q01_q10 = _evidence(value, "q01_q10_full_harness_regression")
    batch_a = _evidence(value, "batch_a_runner_offline_regression")
    _validate_q02(q02)
    _validate_q01_q10(q01_q10)
    _validate_batch_a(batch_a)
    _verify_no_real_activity(q02, q01_q10, batch_a)

    conclusions = value.get("conclusions", {})
    if (
        conclusions.get("q02_primary_defect_owner")
        != "saved_model_report_content"
        or conclusions.get("q02_harness_cascade_defect") != "resolved"
        or conclusions.get("q01_q10_offline_acceptance_consistency")
        != "passed"
        or conclusions.get("batch_a_offline_runner_safety") != "passed"
        or conclusions.get("prompt_boundary_reopen_recommended") is not True
        or conclusions.get("non_report_failure_diagnostic_noise")
        != "open_non_blocking_outside_q02_frozen_scope"
    ):
        raise C1OfflineConsolidatedAuditError(
            "consolidated conclusion drifted from its evidence"
        )

    findings = (
        {
            "id": "C1-F01",
            "status": "resolved",
            "finding": "Q02上游报告失败不再产生正式报告、图表验收或完整性级联错误。",
        },
        {
            "id": "C1-F02",
            "status": "open_decision",
            "finding": "保存的Q02模型报告仍含一个无FACT数值和两处无支持客单价推断。",
        },
        {
            "id": "C1-F03",
            "status": "open_non_blocking",
            "finding": "非报告上游失败夹具仍可能附带Q06图表数量诊断噪声。",
        },
    )
    return C1OfflineConsolidatedAuditResult(
        passed=True,
        q02_summary=q02,
        q01_q10_summary=q01_q10,
        batch_a_summary=batch_a,
        frozen_hashes=frozen_hashes,
        findings=findings,
    )
