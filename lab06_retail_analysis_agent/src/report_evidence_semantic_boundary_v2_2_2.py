"""Offline V2.2.2 audit for report evidence and semantic boundaries."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from src.agent_protocol import FinalReportResponse, parse_control_response
from src.fact_schema import FactRecord
from src.report_validation import ReportDraft, validate_report


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = (
    PROJECT_ROOT
    / "config"
    / "h3_report_evidence_semantic_boundary_v2_2_2.candidate.json"
)
REAL_EVIDENCE_PATH = (
    PROJECT_ROOT
    / "results"
    / "raw"
    / "q06_v2_2_1_flash_real_revalidation_20260803T153719_794668+0800"
    / "Q06.json"
)
CHINESE_DATE_PATTERN = re.compile(
    r"(?P<year>\d{4})年(?P<month>\d{1,2})月"
    r"(?:(?P<day>\d{1,2})日)?"
)
ISO_DATE_PATTERN = re.compile(
    r"\d{4}-\d{2}(?:-\d{2}(?:T\d{2}:\d{2}:\d{2})?)?"
)
GENERIC_NUMBER_PATTERN = re.compile(r"\d[\d,]*(?:\.\d+)?%?")
LEGACY_NUMBER_PATTERN = re.compile(
    r"\d{4}-\d{2}(?:-\d{2}(?:T\d{2}:\d{2}:\d{2})?)?"
    r"|\d[\d,]*(?:\.\d+)?%?"
)


class ReportEvidenceSemanticBoundaryError(ValueError):
    """Raised when the candidate contract or replay evidence drifts."""


@dataclass(frozen=True)
class BoundaryIssue:
    code: str
    location: str
    token_or_phrase: str
    message: str


@dataclass(frozen=True)
class ReportEvidenceSemanticReplay:
    source_sha256: str
    current_numeric_issues: tuple[BoundaryIssue, ...]
    canonical_numeric_issues: tuple[BoundaryIssue, ...]
    deterministic_semantic_issues: tuple[BoundaryIssue, ...]
    manual_review_flags: tuple[BoundaryIssue, ...]
    formal_validation_status: str
    formal_validation_issues: tuple[BoundaryIssue, ...]
    formal_manual_review_flags: tuple[BoundaryIssue, ...]
    terminal_json_parse_passed: bool
    control_schema_passed: bool
    source_response_unchanged: bool


def load_report_evidence_semantic_contract() -> dict[str, Any]:
    value = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ReportEvidenceSemanticBoundaryError(
            "V2.2.2 contract must be a JSON object"
        )
    return value


def canonical_numeric_tokens(text: str) -> set[str]:
    """Return exact numeric tokens with calendar expressions canonicalized."""
    tokens: set[str] = set()
    masked = list(text)
    for pattern in (CHINESE_DATE_PATTERN, ISO_DATE_PATTERN):
        for match in pattern.finditer(text):
            if pattern is CHINESE_DATE_PATTERN:
                year = int(match.group("year"))
                month = int(match.group("month"))
                day = match.group("day")
                token = f"{year:04d}-{month:02d}"
                if day is not None:
                    token += f"-{int(day):02d}"
            else:
                token = match.group(0)
            tokens.add(token)
            for index in range(match.start(), match.end()):
                masked[index] = " "
    remaining = "".join(masked)
    tokens.update(
        match.group(0).replace(",", "")
        for match in GENERIC_NUMBER_PATTERN.finditer(remaining)
    )
    return tokens


def _same_month_scope_token(fact: FactRecord) -> str | None:
    start = fact.analysis_scope.start_date
    end = fact.analysis_scope.end_date
    if start is None or end is None:
        return None
    if len(start) >= 7 and len(end) >= 7 and start[:7] == end[:7]:
        return start[:7]
    return None


def allowed_canonical_tokens(facts: list[FactRecord]) -> set[str]:
    candidates: list[str] = []
    scope_months: set[str] = set()
    for fact in facts:
        candidates.extend(
            [
                fact.value,
                fact.display_value,
                str(fact.rank) if fact.rank is not None else "",
                fact.analysis_scope.start_date or "",
                fact.analysis_scope.end_date or "",
            ]
        )
        candidates.extend(
            dimension.value for dimension in fact.dimensions
        )
        scope_month = _same_month_scope_token(fact)
        if scope_month is not None:
            scope_months.add(scope_month)
    allowed = set(scope_months)
    for candidate in candidates:
        allowed.update(canonical_numeric_tokens(candidate))
    return allowed


def validate_canonical_numeric_evidence(
    draft: ReportDraft,
    facts: list[FactRecord],
) -> tuple[BoundaryIssue, ...]:
    fact_by_id = {fact.fact_id: fact for fact in facts}
    issues: list[BoundaryIssue] = []
    for section_index, section in enumerate(draft.sections):
        for claim_index, claim in enumerate(section.claims):
            location = f"sections[{section_index}].claims[{claim_index}]"
            claim_facts = [
                fact_by_id[reference.fact_id]
                for reference in claim.evidence
                if getattr(reference, "fact_id", None) in fact_by_id
            ]
            unsupported = canonical_numeric_tokens(
                claim.statement
            ) - allowed_canonical_tokens(claim_facts)
            for token in sorted(unsupported):
                issues.append(
                    BoundaryIssue(
                        code="untraceable_numeric_token",
                        location=location,
                        token_or_phrase=token,
                        message=(
                            "规范化后的数值或期间仍没有当前claim的FACT证据。"
                        ),
                    )
                )
    return tuple(issues)


def _claim_facts(
    draft: ReportDraft,
    facts: list[FactRecord],
) -> list[tuple[str, str, list[FactRecord]]]:
    fact_by_id = {fact.fact_id: fact for fact in facts}
    values: list[tuple[str, str, list[FactRecord]]] = []
    for section_index, section in enumerate(draft.sections):
        for claim_index, claim in enumerate(section.claims):
            values.append(
                (
                    f"sections[{section_index}].claims[{claim_index}]",
                    claim.statement,
                    [
                        fact_by_id[reference.fact_id]
                        for reference in claim.evidence
                        if getattr(reference, "fact_id", None) in fact_by_id
                    ],
                )
            )
    return values


def validate_deterministic_semantics(
    draft: ReportDraft,
    facts: list[FactRecord],
) -> tuple[BoundaryIssue, ...]:
    issues: list[BoundaryIssue] = []
    for location, statement, claim_facts in _claim_facts(draft, facts):
        metrics = {fact.metric for fact in claim_facts}
        significance_metrics = {
            "p_value",
            "significance_test",
            "confidence_interval",
        }
        if re.search(r"统计显著|显著性检验|p\s*值", statement) and not (
            metrics & significance_metrics
        ):
            issues.append(
                BoundaryIssue(
                    code="unsupported_significance_claim",
                    location=location,
                    token_or_phrase="统计显著",
                    message="当前claim没有统计显著性FACT。",
                )
            )
        if (
            re.search(r"客单价", statement)
            and canonical_numeric_tokens(statement)
            and not (
            metrics & {"average_order_value", "unit_price"}
            )
        ):
            issues.append(
                BoundaryIssue(
                    code="unsupported_average_value_claim",
                    location=location,
                    token_or_phrase="客单价",
                    message="当前claim没有客单价或单价FACT。",
                )
            )
        superlatives = (
            (
                "unsupported_sales_amount_superlative",
                r"销售额(?:(?![。；]).){0,12}(?:最高|最大|第一)",
                "sales_amount",
                "销售额最高",
            ),
            (
                "unsupported_quantity_superlative",
                r"销量(?:(?![。；]).){0,12}(?:最高|最大)",
                "sales_quantity",
                "销量最高",
            ),
            (
                "unsupported_order_superlative",
                r"订单数(?:(?![。；]).){0,12}(?:最高|最大)",
                "order_count",
                "订单数最高",
            ),
        )
        for code, pattern, metric, phrase in superlatives:
            if re.search(pattern, statement) and not any(
                fact.metric == metric and fact.rank == 1
                for fact in claim_facts
            ):
                issues.append(
                    BoundaryIssue(
                        code=code,
                        location=location,
                        token_or_phrase=phrase,
                        message=(
                            f"当前claim没有rank=1的{metric} FACT。"
                        ),
                    )
                )
    return tuple(issues)


def collect_manual_review_flags(
    draft: ReportDraft,
) -> tuple[BoundaryIssue, ...]:
    rules = (
        (
            "plain_significant_wording",
            r"(?<!统计)显著|明显",
            "非统计程度表达",
        ),
        (
            "unfrozen_average_value_classification",
            r"高客单价",
            "缺少冻结阈值的客单价分类",
        ),
        (
            "product_business_classification",
            r"走量型|走量主力",
            "经营商品分类",
        ),
        ("seasonality_interpretation", r"旺季|销售旺季", "季节性解释"),
        ("inventory_action", r"备货|库存充足|补货周期", "库存行动"),
        (
            "pricing_or_logistics_action",
            r"定价策略|物流策略|优化物流",
            "定价或物流行动",
        ),
        (
            "causal_or_effect_claim",
            r"表明|导致|驱动|维持旺季销售",
            "因果或效果暗示",
        ),
    )
    flags: list[BoundaryIssue] = []
    for section_index, section in enumerate(draft.sections):
        if section.name not in {"有限解释", "经营建议"}:
            continue
        for claim_index, claim in enumerate(section.claims):
            location = f"sections[{section_index}].claims[{claim_index}]"
            for code, pattern, label in rules:
                match = re.search(pattern, claim.statement)
                if match is not None:
                    flags.append(
                        BoundaryIssue(
                            code=code,
                            location=location,
                            token_or_phrase=match.group(0),
                            message=f"{label}必须由人工决定是否接受。",
                        )
                    )
    return tuple(flags)


def _legacy_numeric_tokens(text: str) -> set[str]:
    return {
        match.group(0).replace(",", "")
        for match in LEGACY_NUMBER_PATTERN.finditer(text)
    }


def _legacy_allowed_tokens(facts: list[FactRecord]) -> set[str]:
    candidates: list[str] = []
    for fact in facts:
        candidates.extend(
            [
                fact.value,
                fact.display_value,
                str(fact.rank) if fact.rank is not None else "",
                fact.analysis_scope.start_date or "",
                fact.analysis_scope.end_date or "",
            ]
        )
        candidates.extend(dimension.value for dimension in fact.dimensions)
    allowed: set[str] = set()
    for candidate in candidates:
        allowed.update(_legacy_numeric_tokens(candidate))
    return allowed


def _validate_legacy_numeric_evidence(
    draft: ReportDraft,
    facts: list[FactRecord],
) -> tuple[BoundaryIssue, ...]:
    fact_by_id = {fact.fact_id: fact for fact in facts}
    issues: list[BoundaryIssue] = []
    for section_index, section in enumerate(draft.sections):
        for claim_index, claim in enumerate(section.claims):
            location = f"sections[{section_index}].claims[{claim_index}]"
            claim_facts = [
                fact_by_id[reference.fact_id]
                for reference in claim.evidence
                if getattr(reference, "fact_id", None) in fact_by_id
            ]
            unsupported = _legacy_numeric_tokens(
                claim.statement
            ) - _legacy_allowed_tokens(claim_facts)
            for token in sorted(unsupported):
                issues.append(
                    BoundaryIssue(
                        code="untraceable_numeric_token",
                        location=location,
                        token_or_phrase=token,
                        message="旧校验器中的数值或期间没有FACT证据。",
                    )
                )
    return tuple(issues)


def replay_v2_2_1_real_report(
    evidence_path: Path = REAL_EVIDENCE_PATH,
) -> ReportEvidenceSemanticReplay:
    source_bytes = evidence_path.read_bytes()
    source_hash = sha256(source_bytes).hexdigest()
    payload = json.loads(source_bytes.decode("utf-8"))
    raw_responses = payload["outcome"]["raw_responses"]
    content = raw_responses[2]["choices"][0]["message"]["content"]
    control = parse_control_response(content)
    if not isinstance(control, FinalReportResponse):
        raise ReportEvidenceSemanticBoundaryError(
            "saved Q06 terminal response is not a report"
        )
    facts = [
        FactRecord.model_validate(item)
        for item in payload["outcome"]["facts"]
    ]
    formal_validation = validate_report(control.report, facts)
    current_numeric = _validate_legacy_numeric_evidence(
        control.report,
        facts,
    )
    replay = ReportEvidenceSemanticReplay(
        source_sha256=source_hash,
        current_numeric_issues=current_numeric,
        canonical_numeric_issues=validate_canonical_numeric_evidence(
            control.report,
            facts,
        ),
        deterministic_semantic_issues=validate_deterministic_semantics(
            control.report,
            facts,
        ),
        manual_review_flags=collect_manual_review_flags(control.report),
        formal_validation_status=formal_validation.status,
        formal_validation_issues=tuple(
            BoundaryIssue(
                code=issue.code,
                location=issue.location,
                token_or_phrase="",
                message=issue.message,
            )
            for issue in formal_validation.issues
        ),
        formal_manual_review_flags=tuple(
            BoundaryIssue(
                code=flag.code,
                location=flag.location,
                token_or_phrase="",
                message=flag.message,
            )
            for flag in formal_validation.manual_review_flags
        ),
        terminal_json_parse_passed=True,
        control_schema_passed=True,
        source_response_unchanged=(
            sha256(evidence_path.read_bytes()).hexdigest() == source_hash
        ),
    )
    return replay


def validate_v2_2_2_contract(
    contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    value = contract or load_report_evidence_semantic_contract()
    scope = value.get("scope", {})
    date = value.get("date_equivalence_candidate", {})
    claim = value.get("claim_evidence_candidate", {})
    manual = value.get("manual_semantic_review_candidate", {})
    if value.get("status") not in {
        "offline_investigation_pending_validation_and_user_freeze",
        "offline_validated_pending_user_freeze",
        "frozen_by_user_pending_formal_validator_integration",
        "frozen_by_user_formal_validator_integrated_offline_validated",
    }:
        raise ReportEvidenceSemanticBoundaryError("unexpected V2.2.2 status")
    if (
        scope.get("question_ids") != ["Q06"]
        or scope.get("offline_replay_only") is not True
        or scope.get("real_model_calls_allowed") is not False
        or scope.get("automatic_report_repair_allowed") is not False
        or any(
            scope.get(field) is not False
            for field in (
                "prompt_changed",
                "control_schema_changed",
                "fact_schema_changed",
                "fact_values_changed",
                "seven_tool_whitelist_changed",
                "h2_data_or_metrics_changed",
            )
        )
    ):
        raise ReportEvidenceSemanticBoundaryError("V2.2.2 scope drifted")
    if (
        date.get("global_string_replacement_allowed") is not False
        or date.get("cross_month_scope_may_not_collapse_to_one_month")
        is not True
        or claim.get("claim_local_only") is not True
        or claim.get("cross_claim_fact_borrowing_allowed") is not False
        or claim.get("program_may_add_missing_fact_reference") is not False
        or manual.get("human_remains_final_decision_maker") is not True
        or manual.get("flags_do_not_auto_rewrite_report") is not True
    ):
        raise ReportEvidenceSemanticBoundaryError(
            "V2.2.2 evidence or human boundary drifted"
        )
    if value.get("status") in {
        "frozen_by_user_pending_formal_validator_integration",
        "frozen_by_user_formal_validator_integrated_offline_validated",
    }:
        freeze = value.get("user_freeze", {})
        expected_boundaries = [
            "deterministic_date_equivalence_for_validation_only",
            "strict_claim_local_fact_isolation",
            "deterministic_rejection_of_explicitly_unsupported_semantics",
            "human_final_decision_for_business_interpretation_and_advice",
        ]
        if (
            value.get("frozen_on") != "2026-08-03"
            or freeze.get("status") != "frozen_by_user"
            or freeze.get("frozen_on") != "2026-08-03"
            or freeze.get("frozen_boundaries") != expected_boundaries
            or freeze.get("freeze_does_not_authorize_real_calls")
            is not True
            or freeze.get("freeze_does_not_mark_q06_as_passed")
            is not True
            or freeze.get("freeze_does_not_integrate_formal_validator")
            is not True
        ):
            raise ReportEvidenceSemanticBoundaryError(
                "V2.2.2 user freeze metadata drifted"
            )
    if value.get("status") == (
        "frozen_by_user_formal_validator_integrated_offline_validated"
    ):
        integration = value.get("formal_validator_integration", {})
        mock_regression = integration.get("q01_q10_mock_regression", {})
        if (
            integration.get("status") != "offline_validated"
            or integration.get("source_response_unchanged") is not True
            or integration.get("formal_validation_status") != "failed"
            or integration.get("formal_issue_count") != 8
            or integration.get("canonical_numeric_issue_count") != 1
            or integration.get("deterministic_semantic_issue_count") != 7
            or integration.get("manual_review_flag_count") != 8
            or integration.get("report_rendered") is not False
            or integration.get("automatic_repair_performed") is not False
            or integration.get("real_model_called") is not False
            or mock_regression.get("status") != "passed"
            or mock_regression.get("questions_passed") != 10
            or mock_regression.get("questions_total") != 10
            or mock_regression.get("network_used") is not False
            or mock_regression.get("real_model_called") is not False
            or mock_regression.get("api_key_read") is not False
            or integration.get("full_tests")
            != "228_passed_29_subtests_passed"
        ):
            raise ReportEvidenceSemanticBoundaryError(
                "V2.2.2 formal validator integration evidence drifted"
            )
    return value
