"""Read-only audit of Q01-Q10 acceptance and harness consistency."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from pathlib import Path
from typing import Any

from src.fixed_question_validation import (
    load_frozen_questions,
    validate_fixed_question_legacy as validate_fixed_question,
)
from src.mock_h2_registry import FrozenH2MockRegistry
from src.mock_native_tool_client_v2_1_revision import (
    FrozenQuestionNativeToolMockClient,
)
from src.native_tool_agent_v2_1_revision import (
    RetailNativeToolAgentV2_1Revision,
)
from src.report_evidence_semantic_boundary_v2_2_2 import (
    canonical_numeric_tokens,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = (
    PROJECT_ROOT
    / "config"
    / "h3_q01_q10_acceptance_harness_audit.candidate.json"
)
H2_QUESTIONS_PATH = PROJECT_ROOT / "config" / "h2_validation_questions.json"
V2_2_2_PATH = (
    PROJECT_ROOT
    / "config"
    / "h3_report_evidence_semantic_boundary_v2_2_2.candidate.json"
)
V2_2_3_PATH = (
    PROJECT_ROOT
    / "config"
    / "h3_q06_report_revision_feedback_boundary_v2_2_3.candidate.json"
)
COVERAGE_PATH = (
    PROJECT_ROOT / "config" / "h3_q01_q10_validation_coverage_v2_2_1.json"
)
AUDITED_SOURCE_PATHS = (
    PROJECT_ROOT / "src" / "fixed_question_validation.py",
    PROJECT_ROOT / "src" / "mock_native_tool_client_v2_1_revision.py",
    PROJECT_ROOT / "src" / "fact_builder.py",
    PROJECT_ROOT / "src" / "fact_schema.py",
    PROJECT_ROOT / "src" / "report_validation.py",
    H2_QUESTIONS_PATH,
)


class AcceptanceHarnessAuditError(ValueError):
    """Raised when audit scope or evidence drifts."""


@dataclass(frozen=True)
class QuestionHarnessAudit:
    question_id: str
    question_type: str
    mock_fixed_validation_status: str
    mock_outcome_status: str
    real_mainline_status: str
    report_required: bool
    reference_leaf_count: int
    reference_leaf_covered_by_report: int
    report_reference_coverage_ratio: float | None
    fact_count: int
    report_referenced_fact_count: int
    non_selected_metric_rank_fact_count: int
    request_numeric_tokens: tuple[str, ...]
    request_numeric_source_type_supported: bool
    configured_manual_check_count: int
    returned_manual_review_item_count: int


@dataclass(frozen=True)
class AcceptanceHarnessAuditResult:
    status: str
    questions: tuple[QuestionHarnessAudit, ...]
    findings: tuple[dict[str, Any], ...]
    control_text_probes: dict[str, bool]
    source_hashes_before: dict[str, str]
    source_hashes_after: dict[str, str]
    source_files_unchanged: bool
    real_model_called: bool
    network_used: bool
    api_key_read: bool


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AcceptanceHarnessAuditError(f"JSON object required: {path}")
    return value


def load_acceptance_harness_audit_contract() -> dict[str, Any]:
    return _read_json(CONTRACT_PATH)


def validate_acceptance_harness_audit_contract(
    contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    value = contract or load_acceptance_harness_audit_contract()
    expected_ids = [f"Q{index:02d}" for index in range(1, 11)]
    if value.get("status") not in {
        "offline_audit_pending_validation_and_user_decision",
        "offline_audit_completed_pending_user_decision",
        "findings_accepted_six_boundaries_reopened_offline_design",
    }:
        raise AcceptanceHarnessAuditError("unexpected audit status")
    prerequisite = value.get("prerequisite", {})
    if (
        _read_json(H2_QUESTIONS_PATH).get("status")
        != prerequisite.get("h2_questions_status")
        or _read_json(V2_2_2_PATH).get("status")
        != prerequisite.get("v2_2_2_status")
        or _read_json(V2_2_3_PATH).get("status")
        != prerequisite.get("v2_2_3_status")
    ):
        raise AcceptanceHarnessAuditError("audit prerequisite drifted")
    scope = value.get("scope", {})
    if (
        scope.get("question_ids") != expected_ids
        or scope.get("offline_read_only_audit") is not True
        or scope.get("real_model_calls_allowed") is not False
        or scope.get("api_key_may_be_read") is not False
        or any(
            scope.get(field) is not False
            for field in (
                "validation_rules_changed",
                "mock_changed",
                "prompt_changed",
                "fact_schema_or_builder_changed",
                "tool_or_h2_contract_changed",
                "orchestrator_changed",
                "v2_2_3_resumed",
            )
        )
    ):
        raise AcceptanceHarnessAuditError("audit scope drifted")
    acceptance = value.get("audit_acceptance", {})
    if not all(
        acceptance.get(field) is True
        for field in (
            "run_q01_q10_with_existing_mock_without_modification",
            "preserve_h2_reference_answers",
            "measure_referenced_fact_coverage_of_reference_answer_leaves",
            "detect_non_selected_metric_rank_propagation",
            "probe_q08_q09_q10_unchecked_control_text",
            "separate_mock_protocol_success_from_real_model_evidence",
            "produce_findings_without_implementing_fixes",
            "source_files_must_remain_unchanged",
        )
    ):
        raise AcceptanceHarnessAuditError("audit acceptance drifted")
    authorization = value.get("authorization", {})
    if (
        authorization.get("audit_does_not_freeze_new_acceptance_rules")
        is not True
        or authorization.get("audit_does_not_authorize_fact_schema_change")
        is not True
        or authorization.get("audit_does_not_authorize_mock_or_validator_change")
        is not True
        or authorization.get("audit_does_not_resume_v2_2_3") is not True
        or authorization.get("real_model_calls_allowed") is not False
    ):
        raise AcceptanceHarnessAuditError("audit authorization drifted")
    if value.get("status") in {
        "offline_audit_completed_pending_user_decision",
        "findings_accepted_six_boundaries_reopened_offline_design",
    }:
        offline = value.get("offline_audit", {})
        if (
            offline.get("status") != "passed_with_findings"
            or offline.get("finding_count") != 7
            or offline.get("severity_counts")
            != {"P1": 3, "P2": 3, "P3": 1}
            or offline.get("p0_finding_count") != 0
            or offline.get("mock_fixed_validation_passed") != 10
            or offline.get("targeted_tests") != "16_passed"
            or offline.get("full_tests")
            != "239_passed_29_subtests_passed"
            or offline.get("incomplete_report_questions")
            != ["Q01", "Q02", "Q03", "Q04", "Q05", "Q06", "Q07"]
            or offline.get("rank_ambiguity_fact_counts")
            != {"Q02": 10, "Q03": 10, "Q06": 6}
            or offline.get("source_files_unchanged") is not True
            or offline.get("validation_rules_changed") is not False
            or offline.get("v2_2_3_resumed") is not False
            or offline.get("real_model_called") is not False
        ):
            raise AcceptanceHarnessAuditError(
                "completed audit evidence drifted"
            )
    if value.get("status") == (
        "findings_accepted_six_boundaries_reopened_offline_design"
    ):
        decision = value.get("user_decision", {})
        if (
            decision.get("status") != "audit_findings_accepted"
            or len(decision.get("reopened_boundaries", [])) != 6
            or decision.get("offline_design_only") is not True
            or decision.get("h2_reference_answers_must_not_change")
            is not True
            or decision.get("v2_2_3_must_remain_paused") is not True
            or decision.get("real_model_calls_allowed") is not False
        ):
            raise AcceptanceHarnessAuditError(
                "accepted audit decision drifted"
            )
    return value


def _hash_sources() -> dict[str, str]:
    return {
        path.relative_to(PROJECT_ROOT).as_posix(): sha256(
            path.read_bytes()
        ).hexdigest()
        for path in AUDITED_SOURCE_PATHS
    }


def _flatten_leaves(value: Any, path: str = "") -> list[tuple[str, Any]]:
    if isinstance(value, dict):
        result: list[tuple[str, Any]] = []
        for key, item in value.items():
            child = f"{path}.{key}" if path else key
            result.extend(_flatten_leaves(item, child))
        return result
    if isinstance(value, list):
        result = []
        for index, item in enumerate(value):
            result.extend(_flatten_leaves(item, f"{path}[{index}]"))
        return result
    return [(path, value)]


def _numeric_key(value: Any) -> str | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        decimal = Decimal(str(value).replace(",", "").lstrip("£"))
    except (InvalidOperation, ValueError):
        return None
    normalized = format(decimal.normalize(), "f")
    return normalized.rstrip("0").rstrip(".") if "." in normalized else normalized


def _reference_leaf_is_covered(
    value: Any,
    *,
    report_text: str,
    cited_values: set[str],
    report_numeric_tokens: set[str],
) -> bool:
    numeric = _numeric_key(value)
    if numeric is not None:
        return numeric in cited_values or numeric in report_numeric_tokens
    if value is None:
        return True
    text = str(value).casefold()
    return text in report_text or text in cited_values


def _question_audit(
    question_id: str,
    *,
    question: dict[str, Any],
    outcome: Any,
    real_status: str,
) -> QuestionHarnessAudit:
    validation = validate_fixed_question(question_id, outcome)
    report_required = question_id in {f"Q{index:02d}" for index in range(1, 8)}
    leaves = _flatten_leaves(question["reference_answer"]) if report_required else []
    fact_by_id = {fact.fact_id: fact for fact in outcome.facts}
    referenced_ids = (
        []
        if outcome.report_validation is None
        else outcome.report_validation.referenced_fact_ids
    )
    cited_facts = [
        fact_by_id[fact_id]
        for fact_id in referenced_ids
        if fact_id in fact_by_id
    ]
    cited_values: set[str] = set()
    for fact in cited_facts:
        for candidate in (fact.value, fact.display_value):
            numeric = _numeric_key(candidate)
            cited_values.add(numeric if numeric is not None else candidate.casefold())
        cited_values.add(fact.metric.casefold())
        cited_values.update(item.value.casefold() for item in fact.dimensions)
    report_text = (
        ""
        if outcome.report_draft is None
        else " ".join(
            [outcome.report_draft.title]
            + [
                claim.statement
                for section in outcome.report_draft.sections
                for claim in section.claims
            ]
        ).casefold()
    )
    report_numeric_tokens = {
        _numeric_key(token) or token
        for token in canonical_numeric_tokens(report_text)
    }
    covered = sum(
        _reference_leaf_is_covered(
            leaf,
            report_text=report_text,
            cited_values=cited_values,
            report_numeric_tokens=report_numeric_tokens,
        )
        for _, leaf in leaves
    )
    ambiguous_rank_count = 0
    for call in outcome.tool_calls:
        if call.tool_name not in {"rank_products", "analyze_regions"}:
            continue
        selected_metric = call.arguments.get("metric")
        ambiguous_rank_count += sum(
            fact.rank is not None and fact.metric != selected_metric
            for fact in call.facts
        )
    request_numeric_tokens = tuple(
        sorted(canonical_numeric_tokens(question["question"]))
    )
    return QuestionHarnessAudit(
        question_id=question_id,
        question_type=question["type"],
        mock_fixed_validation_status=validation.status,
        mock_outcome_status=outcome.status,
        real_mainline_status=real_status,
        report_required=report_required,
        reference_leaf_count=len(leaves),
        reference_leaf_covered_by_report=covered,
        report_reference_coverage_ratio=(
            None if not leaves else round(covered / len(leaves), 6)
        ),
        fact_count=len(outcome.facts),
        report_referenced_fact_count=len(set(referenced_ids)),
        non_selected_metric_rank_fact_count=ambiguous_rank_count,
        request_numeric_tokens=request_numeric_tokens,
        request_numeric_source_type_supported=(
            not request_numeric_tokens or not report_required
        ),
        configured_manual_check_count=len(question["manual_checklist"]),
        returned_manual_review_item_count=len(validation.manual_review_items),
    )


def _control_text_probes(outcomes: dict[str, Any]) -> dict[str, bool]:
    q08 = outcomes["Q08"]
    changed_q08 = replace(
        q08,
        clarification=q08.clarification.model_copy(
            update={"message": "占位文本，没有覆盖具体澄清要求。"}
        ),
    )
    q09 = outcomes["Q09"]
    changed_q09 = replace(
        q09,
        boundary=q09.boundary.model_copy(
            update={"supported_alternative": "不受支持的任意替代方案"}
        ),
    )
    q10 = outcomes["Q10"]
    changed_q10 = replace(
        q10,
        boundary=q10.boundary.model_copy(
            update={
                "message": "可以直接预测并自动补货。",
                "supported_alternative": "自动补货",
            }
        ),
    )
    return {
        "q08_placeholder_message_still_passes": (
            validate_fixed_question("Q08", changed_q08).status == "passed"
        ),
        "q09_wrong_supported_alternative_still_passes": (
            validate_fixed_question("Q09", changed_q09).status == "passed"
        ),
        "q10_contradictory_refusal_text_still_passes": (
            validate_fixed_question("Q10", changed_q10).status == "passed"
        ),
    }


def run_acceptance_harness_audit() -> AcceptanceHarnessAuditResult:
    validate_acceptance_harness_audit_contract()
    before = _hash_sources()
    questions = load_frozen_questions()
    coverage = {
        item["question_id"]: item["current_native_flash_real"]
        for item in _read_json(COVERAGE_PATH)["questions"]
    }
    outcomes: dict[str, Any] = {}
    audits: list[QuestionHarnessAudit] = []
    for index in range(1, 11):
        question_id = f"Q{index:02d}"
        outcome = RetailNativeToolAgentV2_1Revision(
            client=FrozenQuestionNativeToolMockClient(),
            registry=FrozenH2MockRegistry(),
        ).run_turn(
            session_id="SESSION-acceptance-harness-audit",
            turn_id=f"TURN-{index:03d}",
            question=questions[question_id]["question"],
            result_root="results/raw/acceptance_harness_audit",
        )
        outcomes[question_id] = outcome
        audits.append(
            _question_audit(
                question_id,
                question=questions[question_id],
                outcome=outcome,
                real_status=coverage[question_id],
            )
        )
    probes = _control_text_probes(outcomes)
    report_gaps = [
        item.question_id
        for item in audits
        if item.report_required
        and item.mock_fixed_validation_status == "passed"
        and item.report_reference_coverage_ratio != 1.0
    ]
    rank_gaps = [
        item.question_id
        for item in audits
        if item.non_selected_metric_rank_fact_count > 0
    ]
    request_source_gaps = [
        item.question_id
        for item in audits
        if item.report_required
        and not item.request_numeric_source_type_supported
    ]
    manual_gaps = [
        item.question_id
        for item in audits
        if item.configured_manual_check_count
        > item.returned_manual_review_item_count
    ]
    real_not_run = [
        item.question_id
        for item in audits
        if item.real_mainline_status == "not_run"
    ]
    findings = (
        {
            "finding_id": "F01",
            "severity": "P1",
            "code": "mock_report_completeness_not_enforced",
            "affected_questions": report_gaps,
            "evidence": "固定验收通过，但报告引用未覆盖全部参考答案叶子字段。",
        },
        {
            "finding_id": "F02",
            "severity": "P1",
            "code": "rank_metric_semantics_ambiguous",
            "affected_questions": rank_gaps,
            "evidence": "按销售额排序时，销量和订单数FACT继承了相同rank。",
        },
        {
            "finding_id": "F03",
            "severity": "P1",
            "code": "control_text_acceptance_gap",
            "affected_questions": ["Q08", "Q09", "Q10"],
            "evidence": probes,
        },
        {
            "finding_id": "F04",
            "severity": "P2",
            "code": "request_parameter_provenance_not_modeled",
            "affected_questions": request_source_gaps,
            "evidence": "报告证据只接受FACT，没有独立的用户请求参数来源。",
        },
        {
            "finding_id": "F05",
            "severity": "P2",
            "code": "manual_checklist_not_enforced_by_program",
            "affected_questions": manual_gaps,
            "evidence": "H2人工清单未被逐项执行，且不应被写成自动通过。",
        },
        {
            "finding_id": "F06",
            "severity": "P2",
            "code": "semantic_hard_rule_policy_ambiguous",
            "affected_questions": ["Q01", "Q02", "Q03", "Q04", "Q05", "Q06", "Q07"],
            "evidence": "普通“显著”和“走量型”当前被确定性硬拒绝，需重新决定是否应转人工。",
        },
        {
            "finding_id": "F07",
            "severity": "P3",
            "code": "mock_success_not_real_model_evidence",
            "affected_questions": real_not_run,
            "evidence": "Mock按question_id脚本化选择；当前主线真实状态仍未知。",
        },
    )
    after = _hash_sources()
    return AcceptanceHarnessAuditResult(
        status="findings_confirmed",
        questions=tuple(audits),
        findings=findings,
        control_text_probes=probes,
        source_hashes_before=before,
        source_hashes_after=after,
        source_files_unchanged=before == after,
        real_model_called=False,
        network_used=False,
        api_key_read=False,
    )
