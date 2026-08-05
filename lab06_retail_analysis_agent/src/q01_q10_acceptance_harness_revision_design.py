"""Offline validator for the six-boundary harness revision design."""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from src.fixed_question_validation import load_frozen_questions
from src.mock_h2_registry import FrozenH2MockRegistry
from src.mock_native_tool_client_v2_1_revision import (
    FrozenQuestionNativeToolMockClient,
)
from src.native_tool_agent_v2_1_revision import (
    RetailNativeToolAgentV2_1Revision,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = (
    PROJECT_ROOT
    / "config"
    / "h3_q01_q10_acceptance_harness_revision_design.candidate.json"
)
AUDIT_PATH = (
    PROJECT_ROOT
    / "config"
    / "h3_q01_q10_acceptance_harness_audit.candidate.json"
)
V2_2_3_PATH = (
    PROJECT_ROOT
    / "config"
    / "h3_q06_report_revision_feedback_boundary_v2_2_3.candidate.json"
)
H2_PATH = PROJECT_ROOT / "config" / "h2_validation_questions.json"
CORE_SOURCE_PATHS = (
    PROJECT_ROOT / "src" / "fixed_question_validation.py",
    PROJECT_ROOT / "src" / "mock_native_tool_client_v2_1_revision.py",
    PROJECT_ROOT / "src" / "fact_builder.py",
    PROJECT_ROOT / "src" / "fact_schema.py",
    PROJECT_ROOT / "src" / "report_validation.py",
    PROJECT_ROOT / "src" / "agent_protocol.py",
    H2_PATH,
)
EXPECTED_LEAF_COUNTS = {
    "Q01": 7,
    "Q02": 27,
    "Q03": 23,
    "Q04": 7,
    "Q05": 14,
    "Q06": 20,
    "Q07": 12,
}
EXPECTED_CURRENT_AMBIGUOUS_RANK_COUNTS = {
    "Q02": 10,
    "Q03": 10,
    "Q06": 6,
}


class AcceptanceHarnessRevisionDesignError(ValueError):
    """Raised when the offline-only revision design drifts."""


@dataclass(frozen=True)
class RevisionDesignPreview:
    status: str
    manifest_leaf_counts: dict[str, int]
    request_record_examples: tuple[dict[str, str], ...]
    current_ambiguous_rank_counts: dict[str, int]
    historical_ambiguous_rank_counts: dict[str, int]
    preview_rank_values_cleared: dict[str, int]
    selected_rank_route: str
    semantic_plain_significant_route: str
    semantic_product_classification_route: str
    mock_status_dimensions: tuple[str, ...]
    q10_candidate_boundary_codes: tuple[str, ...]
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
        raise AcceptanceHarnessRevisionDesignError(
            f"JSON object required: {path}"
        )
    return value


def load_acceptance_harness_revision_design() -> dict[str, Any]:
    return _read_json(CONTRACT_PATH)


def validate_acceptance_harness_revision_design(
    contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    value = contract or load_acceptance_harness_revision_design()
    if value.get("status") not in {
        "offline_design_pending_validation_and_user_freeze",
        "offline_validated_pending_user_freeze",
        "frozen_by_user_offline_validated_not_implemented",
    }:
        raise AcceptanceHarnessRevisionDesignError(
            "unexpected revision design status"
        )
    prerequisite = value.get("prerequisite", {})
    if (
        _read_json(AUDIT_PATH).get("status")
        != prerequisite.get("audit_status")
        or _read_json(V2_2_3_PATH).get("status")
        != prerequisite.get("v2_2_3_status")
        or _read_json(H2_PATH).get("status")
        != prerequisite.get("h2_questions_status")
    ):
        raise AcceptanceHarnessRevisionDesignError(
            "revision design prerequisite drifted"
        )
    scope = value.get("scope", {})
    if (
        scope.get("question_ids")
        != [f"Q{index:02d}" for index in range(1, 11)]
        or scope.get("offline_design_only") is not True
        or scope.get("real_model_calls_allowed") is not False
        or scope.get("api_key_may_be_read") is not False
        or any(
            scope.get(field) is not False
            for field in (
                "h2_reference_answers_changed",
                "current_validator_changed",
                "current_fact_schema_or_builder_changed",
                "current_mock_changed",
                "current_prompt_changed",
                "current_model_control_schema_changed",
                "current_orchestrator_changed",
                "v2_2_3_resumed",
            )
        )
    ):
        raise AcceptanceHarnessRevisionDesignError(
            "revision design scope drifted"
        )
    completeness = value.get("boundary_1_report_completeness", {})
    if (
        completeness.get("required_leaf_counts") != EXPECTED_LEAF_COUNTS
        or completeness.get("report_validation_status_alone_is_sufficient")
        is not False
        or completeness.get("tool_result_matches_reference_answer_alone_is_sufficient")
        is not False
        or completeness.get("all_required_manifest_items_must_be_covered")
        is not True
        or completeness.get("program_may_not_generate_missing_claim")
        is not True
    ):
        raise AcceptanceHarnessRevisionDesignError(
            "report completeness boundary drifted"
        )
    provenance = value.get("boundary_2_provenance", {})
    if (
        set(provenance.get("source_types", {}))
        != {"FACT", "REQUEST", "POLICY"}
        or provenance.get("candidate_report_evidence_union")
        != ["FACT", "REQUEST", "POLICY"]
        or provenance.get("current_report_schema_changed") is not False
        or provenance.get("candidate_request_record", {}).get(
            "model_may_create_or_change"
        )
        is not False
    ):
        raise AcceptanceHarnessRevisionDesignError(
            "provenance boundary drifted"
        )
    rank = value.get("boundary_3_rank_semantics", {})
    if (
        rank.get("selected_route") != "rank_only_on_selected_metric_fact"
        or rank.get("associated_non_selected_metrics_rank") is not None
        or rank.get("new_rank_metric_field_required") is not False
        or rank.get("current_ambiguous_fact_counts")
        != EXPECTED_CURRENT_AMBIGUOUS_RANK_COUNTS
        or rank.get("historical_records_must_not_be_rewritten") is not True
    ):
        raise AcceptanceHarnessRevisionDesignError("rank boundary drifted")
    semantic = value.get("boundary_4_semantic_rules", {})
    if (
        semantic.get("plain_significant_is_not_statistical_hard_fail")
        is not True
        or semantic.get("product_classification_is_not_deterministic_hard_fail")
        is not True
        or semantic.get("unsupported_average_order_value_number_remains_hard_fail")
        is not True
        or semantic.get("human_flags_do_not_change_deterministic_status")
        is not True
        or semantic.get("human_remains_final_decision_maker") is not True
    ):
        raise AcceptanceHarnessRevisionDesignError(
            "semantic boundary drifted"
        )
    mock = value.get("boundary_5_mock_responsibility", {})
    expected_statuses = [
        "protocol_mock_status",
        "dataflow_mock_status",
        "tool_reference_answer_status",
        "report_content_acceptance_status",
        "manual_review_status",
        "real_model_validation_status",
    ]
    if (
        mock.get("mock_decision_source") != "scripted_by_question_id"
        or mock.get("mock_may_claim_real_model_understanding") is not False
        or mock.get("replace_single_pass_with") != expected_statuses
        or mock.get("current_generic_mock_report_may_pass_content_acceptance")
        is not False
    ):
        raise AcceptanceHarnessRevisionDesignError(
            "mock responsibility boundary drifted"
        )
    control = value.get("boundary_6_control_content", {})
    q10_addition = control.get("Q10", {}).get(
        "future_control_schema_addition", {}
    )
    if (
        control.get("Q08", {}).get("candidate_status")
        != "passed_deterministic_pending_manual_review"
        or control.get("Q09", {}).get("candidate_status")
        != "passed_deterministic_pending_manual_review"
        or control.get("Q10", {}).get("candidate_status")
        != "passed_deterministic_pending_manual_review"
        or q10_addition.get("field") != "boundary_codes"
        or q10_addition.get("enum_values")
        != ["forecasting_unsupported", "automatic_replenishment_unsupported"]
        or control.get("current_control_schema_changed") is not False
    ):
        raise AcceptanceHarnessRevisionDesignError(
            "control content boundary drifted"
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
            or offline.get("manifest_leaf_counts") != EXPECTED_LEAF_COUNTS
            or offline.get("current_ambiguous_rank_counts")
            != EXPECTED_CURRENT_AMBIGUOUS_RANK_COUNTS
            or offline.get("negative_probe_passed") != 9
            or offline.get("negative_probe_total") != 9
            or offline.get("source_files_unchanged") is not True
            or offline.get("implementation_performed") is not False
            or offline.get("h2_reference_answers_changed") is not False
            or offline.get("v2_2_3_resumed") is not False
            or offline.get("real_model_called") is not False
            or offline.get("network_used") is not False
            or offline.get("api_key_read") is not False
            or not evidence_path.is_file()
        ):
            raise AcceptanceHarnessRevisionDesignError(
                "offline validation evidence drifted"
            )
        evidence = _read_json(evidence_path)
        if (
            evidence.get("run_id") != offline.get("run_id")
            or evidence.get("status") != "passed"
            or evidence.get("candidate_result")
            != "design_ready_not_implemented"
            or evidence.get("negative_probe_passed") != 9
            or evidence.get("negative_probe_total") != 9
            or evidence.get("h2_reference_answers_changed") is not False
            or evidence.get("v2_2_3_resumed") is not False
            or evidence.get("current_harness_implementation_changed")
            is not False
            or evidence.get("real_model_called") is not False
            or evidence.get("api_key_read_from_environment") is not False
        ):
            raise AcceptanceHarnessRevisionDesignError(
                "saved offline validation evidence drifted"
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
        or authorization.get("h2_reference_answers_may_change") is not False
        or authorization.get("v2_2_3_may_resume") is not False
        or authorization.get("real_model_calls_allowed") is not False
    ):
        raise AcceptanceHarnessRevisionDesignError(
            "revision design authorization drifted"
        )
    if frozen:
        user_freeze = value.get("user_freeze", {})
        if (
            user_freeze.get("frozen_boundaries")
            != [
                "report_completeness",
                "request_and_policy_provenance",
                "rank_semantics",
                "semantic_hard_rule_vs_manual_review",
                "mock_responsibility_and_status_naming",
                "clarification_and_refusal_content",
            ]
            or user_freeze.get(
                "freeze_does_not_authorize_implementation"
            )
            is not True
            or user_freeze.get(
                "freeze_does_not_authorize_real_model_calls"
            )
            is not True
            or user_freeze.get(
                "h2_reference_answers_remain_frozen_unchanged"
            )
            is not True
            or user_freeze.get("v2_2_3_remains_paused") is not True
        ):
            raise AcceptanceHarnessRevisionDesignError(
                "user freeze boundary drifted"
            )
    return value


def _hash_sources() -> dict[str, str]:
    return {
        path.relative_to(PROJECT_ROOT).as_posix(): sha256(
            path.read_bytes()
        ).hexdigest()
        for path in CORE_SOURCE_PATHS
    }


def _leaf_count(value: Any) -> int:
    if isinstance(value, dict):
        return sum(_leaf_count(item) for item in value.values())
    if isinstance(value, list):
        return sum(_leaf_count(item) for item in value)
    return 1


def _current_ambiguous_rank_counts() -> dict[str, int]:
    questions = load_frozen_questions()
    counts: dict[str, int] = {}
    for question_id in ("Q02", "Q03", "Q06"):
        outcome = RetailNativeToolAgentV2_1Revision(
            client=FrozenQuestionNativeToolMockClient(),
            registry=FrozenH2MockRegistry(),
        ).run_turn(
            session_id="SESSION-revision-design-preview",
            turn_id=f"TURN-{int(question_id[1:]):03d}",
            question=questions[question_id]["question"],
            result_root="results/raw/revision_design_preview",
        )
        if outcome.status != "completed":
            raise AcceptanceHarnessRevisionDesignError(
                f"Mock preview did not complete: {question_id}"
            )
        count = 0
        for call in outcome.tool_calls:
            if call.tool_name not in {"rank_products", "analyze_regions"}:
                continue
            selected_metric = call.arguments.get("metric")
            count += sum(
                fact.rank is not None and fact.metric != selected_metric
                for fact in call.facts
            )
        counts[question_id] = count
    return counts


def compile_revision_design_preview() -> RevisionDesignPreview:
    contract = validate_acceptance_harness_revision_design()
    before = _hash_sources()
    questions = load_frozen_questions()
    manifest_counts = {
        question_id: _leaf_count(
            questions[question_id]["reference_answer"]
        )
        for question_id in EXPECTED_LEAF_COUNTS
    }
    current_rank_counts = _current_ambiguous_rank_counts()
    request_examples = tuple(
        {
            "question_id": item["question_id"],
            "parameter_name": item["parameter_name"],
            "value": item["value"],
        }
        for item in contract["boundary_2_provenance"]["request_examples"]
    )
    mock_statuses = tuple(
        contract["boundary_5_mock_responsibility"][
            "replace_single_pass_with"
        ]
    )
    q10_codes = tuple(
        contract["boundary_6_control_content"]["Q10"][
            "future_control_schema_addition"
        ]["enum_values"]
    )
    after = _hash_sources()
    return RevisionDesignPreview(
        status="design_consistent_no_implementation",
        manifest_leaf_counts=manifest_counts,
        request_record_examples=request_examples,
        current_ambiguous_rank_counts=current_rank_counts,
        historical_ambiguous_rank_counts=dict(
            EXPECTED_CURRENT_AMBIGUOUS_RANK_COUNTS
        ),
        preview_rank_values_cleared=dict(
            EXPECTED_CURRENT_AMBIGUOUS_RANK_COUNTS
        ),
        selected_rank_route="rank_only_on_selected_metric_fact",
        semantic_plain_significant_route="human_review",
        semantic_product_classification_route="human_review",
        mock_status_dimensions=mock_statuses,
        q10_candidate_boundary_codes=q10_codes,
        source_hashes_before=before,
        source_hashes_after=after,
        source_files_unchanged=before == after,
        implementation_performed=False,
        real_model_called=False,
        network_used=False,
        api_key_read=False,
    )
