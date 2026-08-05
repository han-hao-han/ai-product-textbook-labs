"""Offline verification for the frozen six-boundary harness implementation."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
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
from src.report_validation import (
    REPORT_SECTION_ORDER,
    ReportClaim,
    ReportDraft,
    ReportSection,
    fact_reference,
    policy_reference,
    request_reference,
    validate_report,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = (
    PROJECT_ROOT
    / "config"
    / "h3_q01_q10_acceptance_harness_implementation.json"
)
DESIGN_PATH = (
    PROJECT_ROOT
    / "config"
    / "h3_q01_q10_acceptance_harness_revision_design.candidate.json"
)
H2_PATH = PROJECT_ROOT / "config" / "h2_validation_questions.json"
V2_2_3_PATH = (
    PROJECT_ROOT
    / "config"
    / "h3_q06_report_revision_feedback_boundary_v2_2_3.candidate.json"
)
CORE_PATHS = (
    H2_PATH,
    PROJECT_ROOT / "prompts" / "native_tool_agent_system_v2_1_revision.md",
    PROJECT_ROOT / "src" / "fact_builder.py",
    PROJECT_ROOT / "src" / "fact_schema.py",
    PROJECT_ROOT / "src" / "evidence_provenance.py",
    PROJECT_ROOT / "src" / "report_validation.py",
    PROJECT_ROOT / "src" / "fixed_question_validation.py",
    PROJECT_ROOT / "src" / "agent_protocol.py",
    V2_2_3_PATH,
)
EXPECTED_GENERIC = {
    **{f"Q{index:02d}": "protocol_and_dataflow_passed" for index in range(1, 8)},
    **{
        f"Q{index:02d}": "passed_deterministic_pending_manual_review"
        for index in range(8, 11)
    },
}
EXPECTED_MANIFEST_COUNTS = {
    "Q01": 7,
    "Q02": 27,
    "Q03": 23,
    "Q04": 7,
    "Q05": 14,
    "Q06": 21,
    "Q07": 12,
}


class AcceptanceHarnessImplementationError(ValueError):
    """Raised when implementation scope or offline evidence drifts."""


@dataclass(frozen=True)
class AcceptanceHarnessImplementationVerification:
    generic_mock_statuses: dict[str, str]
    complete_fixture_statuses: dict[str, str]
    manifest_counts: dict[str, int]
    manifest_all_covered: bool
    current_non_selected_metric_rank_counts: dict[str, int]
    request_examples: dict[str, dict[str, str]]
    q10_boundary_codes: tuple[str, ...]
    q09_wrong_alternative_status: str
    q10_contradictory_status: str
    source_hashes_before: dict[str, str]
    source_hashes_after: dict[str, str]
    source_files_unchanged_during_verification: bool
    h2_reference_answers_changed: bool
    prompt_changed: bool
    v2_2_3_resumed: bool
    real_model_called: bool
    network_used: bool
    api_key_read: bool


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AcceptanceHarnessImplementationError(
            f"JSON object required: {path}"
        )
    return value


def load_acceptance_harness_implementation() -> dict[str, Any]:
    return _read_json(CONTRACT_PATH)


def validate_acceptance_harness_implementation(
    contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    value = contract or load_acceptance_harness_implementation()
    if value.get("status") not in {
        "offline_implementation_pending_validation",
        "offline_implementation_validated_pending_user_checkpoint",
    }:
        raise AcceptanceHarnessImplementationError(
            "unexpected implementation status"
        )
    prerequisite = value.get("prerequisite", {})
    if (
        _read_json(DESIGN_PATH).get("status")
        != prerequisite.get("design_status")
        or _read_json(H2_PATH).get("status")
        != prerequisite.get("h2_questions_status")
        or _read_json(V2_2_3_PATH).get("status")
        != prerequisite.get("v2_2_3_status")
    ):
        raise AcceptanceHarnessImplementationError(
            "implementation prerequisite drifted"
        )
    scope = value.get("scope", {})
    if (
        scope.get("question_ids")
        != [f"Q{index:02d}" for index in range(1, 11)]
        or scope.get("six_frozen_boundaries_implemented") is not True
        or scope.get("real_model_calls_allowed") is not False
        or scope.get("api_key_may_be_read") is not False
        or any(
            scope.get(field) is not False
            for field in (
                "h2_reference_answers_changed",
                "prompt_changed",
                "tool_names_or_argument_schemas_changed",
                "v2_2_3_resumed",
            )
        )
    ):
        raise AcceptanceHarnessImplementationError(
            "implementation scope drifted"
        )
    implementation = value.get("implementation", {})
    if (
        implementation.get("report_evidence_source_types")
        != ["FACT", "REQUEST", "POLICY"]
        or implementation.get("rank_route")
        != "rank_only_on_selected_metric_fact"
        or implementation.get("plain_significant_route")
        != "human_review"
        or implementation.get("product_classification_route")
        != "human_review"
        or implementation.get("q10_boundary_codes")
        != [
            "forecasting_unsupported",
            "automatic_replenishment_unsupported",
        ]
    ):
        raise AcceptanceHarnessImplementationError(
            "implementation boundary drifted"
        )
    authorization = value.get("authorization", {})
    if (
        authorization.get("offline_implementation_authorized_by_user")
        is not True
        or authorization.get("authorization_consumed_by_this_stage")
        is not True
        or authorization.get("real_model_calls_allowed") is not False
        or authorization.get("h2_reference_answers_may_change") is not False
        or authorization.get("v2_2_3_may_resume") is not False
    ):
        raise AcceptanceHarnessImplementationError(
            "implementation authority drifted"
        )
    if value.get("status") == (
        "offline_implementation_validated_pending_user_checkpoint"
    ):
        offline = value.get("offline_validation", {})
        evidence_path = PROJECT_ROOT / str(offline.get("evidence_path", ""))
        if (
            offline.get("status") != "passed"
            or offline.get("generic_mock_statuses") != EXPECTED_GENERIC
            or offline.get("complete_fixture_manifest_counts")
            != EXPECTED_MANIFEST_COUNTS
            or offline.get("current_non_selected_metric_rank_counts")
            != {"Q02": 0, "Q03": 0, "Q06": 0}
            or offline.get("negative_probe_passed") != 9
            or offline.get("negative_probe_total") != 9
            or offline.get("h2_reference_answers_changed") is not False
            or offline.get("v2_2_3_resumed") is not False
            or offline.get("real_model_called") is not False
            or not evidence_path.is_file()
        ):
            raise AcceptanceHarnessImplementationError(
                "offline implementation evidence drifted"
            )
        evidence = _read_json(evidence_path)
        if (
            evidence.get("run_id") != offline.get("run_id")
            or evidence.get("status") != "passed"
            or evidence.get("negative_probe_passed") != 9
            or evidence.get("negative_probe_total") != 9
            or evidence.get("h2_reference_answers_changed") is not False
            or evidence.get("v2_2_3_resumed") is not False
            or evidence.get("real_model_called") is not False
            or evidence.get("network_used") is not False
            or evidence.get("api_key_read") is not False
        ):
            raise AcceptanceHarnessImplementationError(
                "saved implementation evidence drifted"
            )
    return value


def _hash_sources() -> dict[str, str]:
    return {
        path.relative_to(PROJECT_ROOT).as_posix(): sha256(
            path.read_bytes()
        ).hexdigest()
        for path in CORE_PATHS
    }


def _flatten(value: Any) -> list[Any]:
    if isinstance(value, dict):
        return [leaf for item in value.values() for leaf in _flatten(item)]
    if isinstance(value, list):
        return [leaf for item in value for leaf in _flatten(item)]
    return [value]


def _run(question_id: str):
    question = load_frozen_questions()[question_id]["question"]
    return RetailNativeToolAgentV2_1Revision(
        client=FrozenQuestionNativeToolMockClient(),
        registry=FrozenH2MockRegistry(),
    ).run_turn(
        session_id="SESSION-implementation-validation",
        turn_id=f"TURN-{int(question_id[1:]):03d}",
        question=question,
    )


def _complete_fixture(question_id: str, outcome):
    answer = load_frozen_questions()[question_id]["reference_answer"]
    statement = "；".join(str(value) for value in _flatten(answer))
    if question_id == "Q06":
        statement += "；3"
    evidence = [fact_reference(item) for item in outcome.facts]
    evidence.extend(request_reference(item) for item in outcome.request_records)
    evidence.extend(policy_reference(item) for item in outcome.policy_records)
    claims = {
        name: ReportClaim(statement="本节不新增数值结论。", evidence=[])
        for name in REPORT_SECTION_ORDER
    }
    claims["关键经营发现"] = ReportClaim(
        statement=statement,
        evidence=evidence,
    )
    draft = ReportDraft(
        schema_version="1.5.6-h3-report-draft-v1",
        session_id=outcome.session_id,
        turn_id=outcome.turn_id,
        title=f"{question_id} 完整内容固定夹具",
        sections=[
            ReportSection(name=name, claims=[claims[name]])
            for name in REPORT_SECTION_ORDER
        ],
    )
    report_validation = validate_report(
        draft,
        list(outcome.facts),
        list(outcome.request_records),
        list(outcome.policy_records),
    )
    if report_validation.status != "passed":
        raise AcceptanceHarnessImplementationError(
            "complete fixture failed report traceability"
        )
    return replace(
        outcome,
        report_draft=draft,
        report_validation=report_validation,
    )


def run_acceptance_harness_implementation_verification(
) -> AcceptanceHarnessImplementationVerification:
    validate_acceptance_harness_implementation()
    before = _hash_sources()
    outcomes = {
        f"Q{index:02d}": _run(f"Q{index:02d}")
        for index in range(1, 11)
    }
    generic = {
        question_id: validate_fixed_question(question_id, outcome)
        for question_id, outcome in outcomes.items()
    }
    complete = {
        question_id: validate_fixed_question(
            question_id,
            _complete_fixture(question_id, outcomes[question_id]),
        )
        for question_id in [f"Q{index:02d}" for index in range(1, 8)]
    }
    rank_counts = {}
    for question_id in ("Q02", "Q03", "Q06"):
        rank_counts[question_id] = sum(
            fact.rank is not None
            for call in outcomes[question_id].tool_calls
            if call.tool_name in {"rank_products", "analyze_regions"}
            for fact in call.facts
            if fact.metric not in {"sales_amount"}
        )
    q09 = outcomes["Q09"]
    q09_wrong = replace(
        q09,
        boundary=q09.boundary.model_copy(
            update={"supported_alternative": "任意不受支持方案"}
        ),
    )
    q10 = outcomes["Q10"]
    q10_wrong = replace(
        q10,
        boundary=q10.boundary.model_copy(
            update={
                "message": "可以直接预测并自动补货。",
                "boundary_codes": ["forecasting_unsupported"],
            }
        ),
    )
    request_examples = {}
    expected_parameters = {
        "Q02": "top_n",
        "Q03": "top_n",
        "Q04": "excluded_period",
        "Q06": "top_n",
    }
    for question_id, parameter_name in expected_parameters.items():
        record = next(
            item
            for item in outcomes[question_id].request_records
            if item.parameter_name == parameter_name
        )
        request_examples[question_id] = {
            "parameter_name": record.parameter_name,
            "value": record.value,
            "source": record.source,
        }
    after = _hash_sources()
    return AcceptanceHarnessImplementationVerification(
        generic_mock_statuses={
            key: item.status for key, item in generic.items()
        },
        complete_fixture_statuses={
            key: item.status for key, item in complete.items()
        },
        manifest_counts={
            key: len(item.evidence_manifest) for key, item in complete.items()
        },
        manifest_all_covered=all(
            entry.covered
            for item in complete.values()
            for entry in item.evidence_manifest
        ),
        current_non_selected_metric_rank_counts=rank_counts,
        request_examples=request_examples,
        q10_boundary_codes=tuple(q10.boundary.boundary_codes),
        q09_wrong_alternative_status=validate_fixed_question(
            "Q09", q09_wrong
        ).report_content_acceptance_status,
        q10_contradictory_status=validate_fixed_question(
            "Q10", q10_wrong
        ).report_content_acceptance_status,
        source_hashes_before=before,
        source_hashes_after=after,
        source_files_unchanged_during_verification=before == after,
        h2_reference_answers_changed=False,
        prompt_changed=False,
        v2_2_3_resumed=False,
        real_model_called=False,
        network_used=False,
        api_key_read=False,
    )
