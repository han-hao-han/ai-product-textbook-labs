"""Concentrated offline audit for the frozen Q02 terminal revision."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = (
    PROJECT_ROOT
    / "config"
    / "h3_q02_terminal_capacity_truncation_transport_audit_revision_implementation.json"
)


class Q02TerminalRevisionConcentratedAuditError(ValueError):
    """Raised when implementation or frozen evidence drifts."""


@dataclass(frozen=True)
class Q02TerminalRevisionConcentratedAuditResult:
    passed: bool
    evidence_checks: dict[str, bool]
    implementation_hashes_match: bool
    frozen_hashes_match: bool
    q02_root_code: str
    q01_q10_mock_passed: int
    q01_q10_transport_passed: int
    harness_negative_probes_passed: int
    batch_a_offline_status: str
    full_test_status: str


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Q02TerminalRevisionConcentratedAuditError(
            f"JSON object required: {path.name}"
        )
    return value


def _hash(relative: str) -> str:
    return sha256((PROJECT_ROOT / relative).read_bytes()).hexdigest()


def load_q02_terminal_revision_implementation_contract() -> dict[str, Any]:
    return _read_json(CONTRACT_PATH)


def validate_q02_terminal_revision_implementation_contract(
    contract: dict[str, Any] | None = None,
) -> Q02TerminalRevisionConcentratedAuditResult:
    value = contract or load_q02_terminal_revision_implementation_contract()
    if value.get("status") not in {
        "offline_implementation_and_full_regression_completed_pending_concentrated_audit",
        "offline_implementation_full_regression_and_concentrated_audit_completed",
    }:
        raise Q02TerminalRevisionConcentratedAuditError(
            "unexpected implementation status"
        )

    authorization = value.get("authorization", {})
    if any(
        authorization.get(field) is not False
        for field in (
            "real_model_calls_allowed",
            "h2_changes_allowed",
            "prompt_changes_allowed",
            "tool_report_fact_chart_schema_changes_allowed",
            "acceptance_root_rule_changes_allowed",
            "batch_b_authorized",
            "v2_2_3_resume_allowed",
        )
    ):
        raise Q02TerminalRevisionConcentratedAuditError(
            "offline authorization boundary widened"
        )

    implementation = value.get("implementation_files", {})
    frozen = value.get("frozen_sources", {})
    implementation_hashes_match = bool(implementation) and all(
        _hash(path) == expected for path, expected in implementation.items()
    )
    frozen_hashes_match = bool(frozen) and all(
        _hash(path) == expected for path, expected in frozen.items()
    )
    if not implementation_hashes_match or not frozen_hashes_match:
        raise Q02TerminalRevisionConcentratedAuditError(
            "implementation or frozen source hash drifted"
        )

    evidence = value.get("offline_evidence", {})
    loaded = {
        name: _read_json(PROJECT_ROOT / str(item["path"]))
        for name, item in evidence.items()
    }
    q02 = loaded["saved_q02_regression"]
    mock = loaded["q01_q10_native_mock"]
    transport = loaded["q01_q10_native_transport"]
    harness = loaded["q01_q10_acceptance_harness"]
    batch = loaded["batch_a_safe_runner"]
    evidence_checks = {
        "q02_saved_response": (
            q02.get("status") == "passed"
            and q02.get("batch_primary_stop_codes")
            == ["terminal_output_truncated"]
            and q02.get("tool_reference_answer_status") == "passed"
            and q02.get("request_max_tokens") == [4096, 8192]
            and "q02_chart_count_mismatch"
            not in q02.get("batch_program_failures", [])
        ),
        "q01_q10_mock": (
            mock.get("status") == "passed"
            and mock.get("questions_passed") == 10
            and mock.get("questions_total") == 10
        ),
        "q01_q10_transport": (
            transport.get("status") == "passed"
            and transport.get("fixed_questions_passed") == 10
            and transport.get("fixed_questions_total") == 10
            and transport.get("request_count") == 20
            and transport.get("request_contract_passed") is True
        ),
        "acceptance_harness": (
            harness.get("status") == "passed"
            and harness.get("negative_probe_passed") == 9
            and harness.get("negative_probe_total") == 9
            and harness.get("verification", {}).get("manifest_all_covered")
            is True
        ),
        "batch_a_safe_runner": (
            batch.get("status") == "passed"
            and batch.get("success_scenario", {}).get("status")
            == "passed_deterministic_pending_manual_review"
            and batch.get("authorization_gate", {}).get("blocked") is True
            and batch.get("evidence_safety", {}).get("api_key_saved")
            is False
        ),
        "offline_only": all(
            item.get("real_model_called") is False
            and item.get("network_used", item.get("real_network_opened"))
            is False
            for item in loaded.values()
        ),
    }
    if not all(evidence_checks.values()):
        raise Q02TerminalRevisionConcentratedAuditError(
            "one or more offline evidence checks failed"
        )
    tests = value.get("test_results", {})
    if tests.get("full") != "334_passed_63_subtests_passed":
        raise Q02TerminalRevisionConcentratedAuditError(
            "full regression status is missing"
        )
    return Q02TerminalRevisionConcentratedAuditResult(
        passed=True,
        evidence_checks=evidence_checks,
        implementation_hashes_match=implementation_hashes_match,
        frozen_hashes_match=frozen_hashes_match,
        q02_root_code=q02["batch_primary_stop_codes"][0],
        q01_q10_mock_passed=int(mock["questions_passed"]),
        q01_q10_transport_passed=int(transport["fixed_questions_passed"]),
        harness_negative_probes_passed=int(harness["negative_probe_passed"]),
        batch_a_offline_status=str(batch["status"]),
        full_test_status=str(tests["full"]),
    )


def negative_audit_contracts() -> list[dict[str, Any]]:
    base = load_q02_terminal_revision_implementation_contract()
    probes = []
    for section, field, replacement in (
        ("authorization", "real_model_calls_allowed", True),
        ("authorization", "batch_b_authorized", True),
        ("authorization", "v2_2_3_resume_allowed", True),
        ("test_results", "full", "not_run"),
    ):
        changed = deepcopy(base)
        changed[section][field] = replacement
        probes.append(changed)
    drift = deepcopy(base)
    first = next(iter(drift["frozen_sources"]))
    drift["frozen_sources"][first] = "0" * 64
    probes.append(drift)
    return probes
