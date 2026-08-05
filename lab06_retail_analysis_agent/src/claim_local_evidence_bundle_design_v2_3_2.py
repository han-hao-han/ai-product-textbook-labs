"""Offline design validation for the V2.3.2 claim-evidence bundles."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DESIGN_PATH = (
    PROJECT_ROOT
    / "config"
    / "h3_claim_local_evidence_bundle_v2_3_2.candidate.json"
)
REAL_RUN_DIR = (
    PROJECT_ROOT
    / "results"
    / "raw"
    / "batch_a_report_admissible_v2_3_1_20260804T131120_351077+0800"
)


class ClaimEvidenceBundleDesignError(ValueError):
    """Raised when the V2.3.2 candidate widens or contradicts its boundary."""


@dataclass(frozen=True)
class ClaimEvidenceBundleDesignAudit:
    status: str
    design_status: str
    frozen_source_hashes_match: bool
    real_q02_root_cause_matches: bool
    generic_grouping_only: bool
    model_report_responsibility_preserved: bool
    claim_local_validator_preserved: bool
    q02_selection_limit_dependency_distinguished: bool
    implementation_authorized: bool
    real_model_called: bool


def _object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ClaimEvidenceBundleDesignError(f"object required: {path}")
    return value


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_design() -> ClaimEvidenceBundleDesignAudit:
    design = _object(DESIGN_PATH)
    selected = design.get("selected_boundary", {})
    envelope = design.get("terminal_envelope_candidate", {})
    bundle = design.get("bundle_schema_candidate", {})
    usage = design.get("bundle_usage_contract", {})
    failure = design.get("fail_closed_rules", {})
    exclusions = design.get("scope_exclusions", {})
    gate = design.get("implementation_gate", {})
    if (
        design.get("status")
        != "frozen_by_user_offline_implementation_validated"
        or selected.get("stage")
        != "after_tool_chain_before_report_terminal"
        or selected.get("authority") != "deterministic_program"
        or selected.get("question_id_specific_mapping_allowed") is not False
        or selected.get("free_text_claim_generation_by_program_allowed")
        is not False
        or selected.get("program_selected_business_conclusion_allowed")
        is not False
        or selected.get("post_hoc_evidence_injection_allowed") is not False
        or selected.get("report_output_repair_allowed") is not False
        or envelope.get("tool_evidence_unchanged_from") != "V2.3.1"
        or envelope.get("report_schema_changed") is not False
        or envelope.get("bundle_ids_appear_in_report_output") is not False
        or envelope.get("report_claims_still_embed_full_reference_objects")
        is not True
        or "claim_text" not in bundle.get("forbidden_fields", [])
        or usage.get("model_may_choose_which_supported_claims_to_write")
        is not True
        or usage.get("combined_claim_requires_union_of_atom_evidence_in_same_claim")
        is not True
        or usage.get("evidence_in_another_claim_does_not_satisfy_current_claim")
        is not True
        or usage.get("existing_report_validator_remains_final_authority")
        is not True
        or failure.get("model_report_missing_local_evidence_still_rejected")
        is not True
        or failure.get("automatic_retry_count") != 0
        or failure.get("model_failure_feedback_loop_enabled") is not False
        or any(value is not False for value in exclusions.values())
        or gate.get("current_phase") != "offline_implementation_completed"
        or gate.get("implementation_authorized") is not True
        or gate.get("freeze_required_before_implementation") is not True
    ):
        raise ClaimEvidenceBundleDesignError("V2.3.2 design boundary drifted")

    for relative, expected in design["frozen_source_hashes"].items():
        if _hash(PROJECT_ROOT / relative) != expected:
            raise ClaimEvidenceBundleDesignError(
                f"frozen source hash drifted: {relative}"
            )

    real_case = _object(REAL_RUN_DIR / "Q02.json")
    real_audit = _object(REAL_RUN_DIR / "concentrated_audit.json")
    outcome = real_case["outcome"]
    fact_one = next(
        fact for fact in outcome["facts"] if fact["fact_id"] == "FACT-001"
    )
    example = design["q02_explanatory_example"]
    selection = example["selection_limit_bundle"]["support_atom"]
    failed_ids = set(example["failed_real_claim_evidence_ids"])
    required_union = set(example["required_evidence_union_for_same_claim"])
    real_q02_matches = (
        real_audit["status"] == "root_cause_confirmed"
        and real_audit["root_failure"]["unsupported_token"] == "5"
        and real_audit["root_failure"]["required_local_evidence_id"]
        == "FACT-001"
        and fact_one["metric"] == "top_n"
        and fact_one["value"] == "5"
    )
    dependency_distinguished = (
        selection["semantic_role"] == "selection_limit"
        and selection["evidence_ids"] == ["FACT-001"]
        and "FACT-001" not in failed_ids
        and required_union == failed_ids | {"FACT-001"}
        and example["program_may_auto_apply_union_to_model_output"] is False
    )
    if not real_q02_matches or not dependency_distinguished:
        raise ClaimEvidenceBundleDesignError(
            "Q02 design example does not match saved real evidence"
        )

    return ClaimEvidenceBundleDesignAudit(
        status="passed",
        design_status=design["status"],
        frozen_source_hashes_match=True,
        real_q02_root_cause_matches=True,
        generic_grouping_only=True,
        model_report_responsibility_preserved=True,
        claim_local_validator_preserved=True,
        q02_selection_limit_dependency_distinguished=True,
        implementation_authorized=True,
        real_model_called=False,
    )


__all__ = [
    "ClaimEvidenceBundleDesignAudit",
    "ClaimEvidenceBundleDesignError",
    "validate_design",
]
