"""Formal offline validation for the native report Prompt evidence guard."""

from __future__ import annotations

import json
from dataclasses import dataclass, fields
from hashlib import sha256
from pathlib import Path
from typing import Any

from src.fixed_question_validation import (
    load_frozen_questions,
    validate_fixed_question,
)
from src.mock_h2_registry import FrozenH2MockRegistry
from src.mock_native_tool_client_v2_1_revision import (
    FrozenQuestionNativeToolMockClient,
)
from src.native_tool_agent_v2_1_revision import (
    RetailNativeToolAgentV2_1Revision,
)
from src.prompt_contract import (
    load_native_tool_agent_prompts_evidence_guard_v1,
)
from src.q02_failure_harness_revision_implementation import (
    ROOT_CODES,
    SAVED_CASE_PATH,
    SavedQ02FailureClient,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ACCEPTED_OFFLINE_HARNESS_STATUSES = {
    "protocol_and_dataflow_passed",
    "passed_deterministic_pending_manual_review",
}
CONTRACT_PATH = (
    PROJECT_ROOT
    / "config"
    / "h3_native_report_prompt_evidence_guard_implementation.json"
)
DESIGN_PATH = (
    PROJECT_ROOT
    / "config"
    / "h3_native_report_prompt_evidence_guard_design.candidate.json"
)


class NativeReportPromptEvidenceGuardImplementationError(ValueError):
    """Raised when implementation or frozen-source evidence drifts."""


@dataclass(frozen=True)
class NativeReportPromptEvidenceGuardImplementationResult:
    passed: bool
    prompt_version: str
    prompt_relative_path: str
    predecessor_file_sha256: str
    active_file_sha256: str
    active_loaded_content_sha256: str
    saved_q02_sha256: str
    saved_q02_status: str
    saved_q02_tool_reference_answer_status: str
    saved_q02_root_failure_codes: tuple[str, ...]
    q01_q10_statuses: dict[str, str]
    q01_q10_passed: int
    q01_q10_total: int
    runtime_prompt_contains_all_guards: bool
    frozen_hashes: dict[str, str]


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise NativeReportPromptEvidenceGuardImplementationError(
            f"JSON object required: {path.name}"
        )
    return value


def _hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def load_native_report_prompt_evidence_guard_implementation(
) -> dict[str, Any]:
    return _read_json(CONTRACT_PATH)


def _validate_exact_additive_prompt(
    contract: dict[str, Any], design: dict[str, Any]
) -> tuple[str, str]:
    versioning = contract["prompt_versioning"]
    predecessor_path = PROJECT_ROOT / versioning["frozen_predecessor_path"]
    active_path = PROJECT_ROOT / versioning["new_active_path"]
    predecessor = predecessor_path.read_text(encoding="utf-8").rstrip()
    rules = design["candidate_additive_rules"]
    additions = "\n".join(
        f'{index}. `[{rule["rule_id"]}]` {rule["text"]}'
        for index, rule in enumerate(rules, start=8)
    )
    expected = f"{predecessor}\n\n{additions}"
    observed = active_path.read_text(encoding="utf-8").rstrip()
    if observed != expected:
        raise NativeReportPromptEvidenceGuardImplementationError(
            "new Prompt is not the exact predecessor plus the three frozen rules"
        )
    return _hash(predecessor_path), _hash(active_path)


def _validate_frozen_hashes(contract: dict[str, Any]) -> dict[str, str]:
    expected = contract["frozen_source_hashes"]
    observed = {
        relative: _hash(PROJECT_ROOT / relative)
        for relative in expected
    }
    if observed != expected:
        raise NativeReportPromptEvidenceGuardImplementationError(
            "H2, data, Schema, validator, or V2.2.3 frozen source drifted"
        )
    return observed


class _CapturingSavedQ02Client(SavedQ02FailureClient):
    def __init__(self) -> None:
        super().__init__()
        self.system_prompts: list[str] = []

    def complete_strict_tools(self, **kwargs):
        self.system_prompts.append(kwargs["messages"][0]["content"])
        return super().complete_strict_tools(**kwargs)


def validate_native_report_prompt_evidence_guard_implementation(
    contract: dict[str, Any] | None = None,
) -> NativeReportPromptEvidenceGuardImplementationResult:
    value = contract or load_native_report_prompt_evidence_guard_implementation()
    if value.get("status") not in {
        "offline_implementation_pending_formal_validation",
        "offline_implementation_validated_pending_user_checkpoint",
        "offline_implementation_and_full_regression_completed_pending_separate_real_validation_authorization",
    }:
        raise NativeReportPromptEvidenceGuardImplementationError(
            "unexpected implementation status"
        )
    design = _read_json(DESIGN_PATH)
    if design.get("status") != (
        "frozen_by_user_offline_validated_implementation_authorized"
    ):
        raise NativeReportPromptEvidenceGuardImplementationError(
            "frozen and authorized design prerequisite drifted"
        )
    authorization = value.get("authorization", {})
    if authorization.get("status") != "authorized_by_user_after_candidate_freeze":
        raise NativeReportPromptEvidenceGuardImplementationError(
            "implementation authorization is missing"
        )
    if any(
        item is not False
        for key, item in authorization.items()
        if key not in {"status", "design"}
    ):
        raise NativeReportPromptEvidenceGuardImplementationError(
            "implementation authorization widened"
        )
    exclusions = value.get("persistent_exclusions", {})
    if not exclusions or any(item is not False for item in exclusions.values()):
        raise NativeReportPromptEvidenceGuardImplementationError(
            "persistent exclusion drifted"
        )
    if value.get("status") == (
        "offline_implementation_and_full_regression_completed_pending_separate_real_validation_authorization"
    ):
        offline = value.get("offline_validation", {})
        evidence_sections = (
            "formal_implementation",
            "saved_q02_regression",
            "q01_q10_native_mock",
            "q01_q10_acceptance_harness",
            "q01_q10_offline_transport",
            "batch_a_safe_runner",
        )
        if (
            offline.get("status") != "passed"
            or any(
                not (
                    PROJECT_ROOT
                    / str(offline.get(section, {}).get("evidence_path", ""))
                ).is_file()
                for section in evidence_sections
            )
            or offline.get("q01_q10_native_mock", {}).get("passed") != 10
            or offline.get("q01_q10_offline_transport", {}).get("passed")
            != 10
            or offline.get("q01_q10_offline_transport", {}).get(
                "request_contract_passed"
            )
            is not True
            or offline.get("batch_a_safe_runner", {}).get("status")
            != "passed"
            or offline.get("tests", {}).get("full")
            != "312_passed_49_subtests_passed"
            or offline.get("frozen_sources_unchanged") is not True
            or any(
                offline.get(field) is not False
                for field in (
                    "real_model_called",
                    "network_used",
                    "api_key_read",
                    "v2_2_3_resumed",
                )
            )
        ):
            raise NativeReportPromptEvidenceGuardImplementationError(
                "completed offline regression evidence drifted"
            )

    predecessor_hash, active_hash = _validate_exact_additive_prompt(
        value, design
    )
    versioning = value["prompt_versioning"]
    if (
        predecessor_hash != versioning["frozen_predecessor_file_sha256"]
        or active_hash != versioning["new_active_file_sha256"]
        or versioning["additional_rules_beyond_frozen_predecessor"] != 3
        or versioning["frozen_predecessor_modified"] is not False
    ):
        raise NativeReportPromptEvidenceGuardImplementationError(
            "Prompt version hashes or additive rule count drifted"
        )
    prompts = load_native_tool_agent_prompts_evidence_guard_v1()
    default_factory = next(
        item.default_factory
        for item in fields(RetailNativeToolAgentV2_1Revision)
        if item.name == "prompts"
    )
    default_prompts = default_factory()
    if (
        prompts.report.version != versioning["new_active_version"]
        or prompts.report.relative_path != versioning["new_active_path"]
        or prompts.report.sha256
        != versioning["new_active_loaded_content_sha256"]
        or default_prompts.report != prompts.report
    ):
        raise NativeReportPromptEvidenceGuardImplementationError(
            "native mainline is not wired to the evidence-guard Prompt"
        )

    frozen_hashes = _validate_frozen_hashes(value)
    q02_client = _CapturingSavedQ02Client()
    q02_outcome = RetailNativeToolAgentV2_1Revision(
        client=q02_client,
        registry=FrozenH2MockRegistry(),
    ).run_turn(
        session_id="SESSION-evidence-guard-saved-q02",
        turn_id="TURN-002",
        question=load_frozen_questions()["Q02"]["question"],
        result_root="results/raw/evidence_guard_saved_q02",
    )
    q02_validation = validate_fixed_question("Q02", q02_outcome)
    rejected = q02_outcome.rejected_report_evidence
    q02_codes = tuple(
        item.code for item in rejected.report_validation.issues
    ) if rejected is not None else ()
    runtime_has_guards = bool(q02_client.system_prompts) and all(
        all(rule_id in prompt for rule_id in versioning["additive_rule_ids"])
        for prompt in q02_client.system_prompts
    )

    q01_q10_statuses: dict[str, str] = {}
    questions = load_frozen_questions()
    for index in range(1, 11):
        question_id = f"Q{index:02d}"
        outcome = RetailNativeToolAgentV2_1Revision(
            client=FrozenQuestionNativeToolMockClient(),
            registry=FrozenH2MockRegistry(),
        ).run_turn(
            session_id="SESSION-evidence-guard-q01-q10",
            turn_id=f"TURN-{index:03d}",
            question=questions[question_id]["question"],
            result_root="results/raw/evidence_guard_q01_q10",
        )
        q01_q10_statuses[question_id] = validate_fixed_question(
            question_id, outcome
        ).status
    q01_q10_passed = sum(
        status in ACCEPTED_OFFLINE_HARNESS_STATUSES
        for status in q01_q10_statuses.values()
    )

    expected = value["expected_offline_results"]
    passed = (
        q02_outcome.status == "failed"
        and q02_outcome.error_stage == "report_validation"
        and q02_validation.tool_reference_answer_status == "passed"
        and list(q02_codes) == ROOT_CODES
        and _hash(SAVED_CASE_PATH)
        == "b0bd08dfcd7e5ee080903679735fcb4b5f65df95330ea3148143d8cd2dd8891d"
        and runtime_has_guards
        and q01_q10_passed == expected["q01_q10_mock_questions_passed"]
        and len(q01_q10_statuses) == expected["q01_q10_mock_questions_total"]
    )
    return NativeReportPromptEvidenceGuardImplementationResult(
        passed=passed,
        prompt_version=prompts.report.version,
        prompt_relative_path=prompts.report.relative_path,
        predecessor_file_sha256=predecessor_hash,
        active_file_sha256=active_hash,
        active_loaded_content_sha256=prompts.report.sha256,
        saved_q02_sha256=_hash(SAVED_CASE_PATH),
        saved_q02_status=(
            "failed_stopped" if q02_outcome.status == "failed" else q02_outcome.status
        ),
        saved_q02_tool_reference_answer_status=(
            q02_validation.tool_reference_answer_status
        ),
        saved_q02_root_failure_codes=q02_codes,
        q01_q10_statuses=q01_q10_statuses,
        q01_q10_passed=q01_q10_passed,
        q01_q10_total=len(q01_q10_statuses),
        runtime_prompt_contains_all_guards=runtime_has_guards,
        frozen_hashes=frozen_hashes,
    )
