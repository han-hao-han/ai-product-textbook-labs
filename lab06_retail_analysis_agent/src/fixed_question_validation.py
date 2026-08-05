"""Deterministic checks for the ten frozen H2 validation questions."""

from __future__ import annotations

import calendar
import json
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.agent_orchestrator import AgentTurnOutcome
from src.deepseek_client import provider_output_was_truncated
from src.evidence_provenance import PolicyRecord, RequestRecord
from src.fact_schema import FactRecord
from src.report_evidence_semantic_boundary_v2_2_2 import (
    canonical_numeric_tokens,
)
from src.report_validation import (
    ReportFactReference,
    ReportPolicyReference,
    ReportRequestReference,
)


QUESTION_CONFIG_PATH = (
    Path(__file__).resolve().parents[1]
    / "config"
    / "h2_validation_questions.json"
)


class StrictValidationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class FixedQuestionIssue(StrictValidationModel):
    path: str
    expected: str
    observed: str


class LegacyFixedQuestionValidationResult(StrictValidationModel):
    schema_version: Literal[
        "1.5.6-h3-fixed-question-validation-v1"
    ]
    question_id: str = Field(pattern=r"^Q\d{2}$")
    status: Literal["passed", "failed"]
    deterministic_checks: list[str]
    issues: list[FixedQuestionIssue]
    manual_review_items: list[str]


class EvidenceManifestItem(StrictValidationModel):
    path: str
    source_type: Literal["FACT", "REQUEST", "POLICY"]
    expected: str
    covered: bool
    evidence_ids: list[str]


class FixedQuestionValidationResult(StrictValidationModel):
    schema_version: Literal[
        "1.5.6-h3-fixed-question-validation-v2"
    ]
    question_id: str = Field(pattern=r"^Q\d{2}$")
    status: Literal[
        "failed",
        "protocol_and_dataflow_passed",
        "passed_deterministic_pending_manual_review",
    ]
    protocol_mock_status: Literal["passed", "not_applicable"]
    dataflow_mock_status: Literal["passed", "failed"]
    tool_reference_answer_status: Literal[
        "passed",
        "failed",
        "not_applicable",
    ]
    report_content_acceptance_status: Literal[
        "passed",
        "failed",
        "not_applicable",
        "not_evaluated_due_to_upstream_report_validation_failure",
        "not_evaluated_due_to_terminal_output_truncation",
    ]
    manual_review_status: Literal["pending"]
    real_model_validation_status: Literal[
        "current_model_real_status_unknown"
    ]
    deterministic_checks: list[str]
    issues: list[FixedQuestionIssue]
    evidence_manifest: list[EvidenceManifestItem]
    manual_review_items: list[str]


def load_frozen_questions() -> dict[str, dict[str, Any]]:
    payload = json.loads(
        QUESTION_CONFIG_PATH.read_text(encoding="utf-8")
    )
    return {
        question["id"]: question
        for question in payload["questions"]
    }


def _stable(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _compare_subset(
    expected: Any,
    observed: Any,
    *,
    path: str,
    issues: list[FixedQuestionIssue],
) -> None:
    if isinstance(expected, dict):
        if not isinstance(observed, dict):
            issues.append(
                FixedQuestionIssue(
                    path=path,
                    expected=_stable(expected),
                    observed=_stable(observed),
                )
            )
            return
        for key, value in expected.items():
            if key not in observed:
                issues.append(
                    FixedQuestionIssue(
                        path=f"{path}.{key}",
                        expected=_stable(value),
                        observed="<missing>",
                    )
                )
                continue
            _compare_subset(
                value,
                observed[key],
                path=f"{path}.{key}",
                issues=issues,
            )
        return
    if isinstance(expected, list):
        if not isinstance(observed, list) or len(expected) != len(
            observed
        ):
            issues.append(
                FixedQuestionIssue(
                    path=path,
                    expected=_stable(expected),
                    observed=_stable(observed),
                )
            )
            return
        for index, value in enumerate(expected):
            _compare_subset(
                value,
                observed[index],
                path=f"{path}[{index}]",
                issues=issues,
            )
        return
    if expected != observed:
        issues.append(
            FixedQuestionIssue(
                path=path,
                expected=_stable(expected),
                observed=_stable(observed),
            )
        )


def _call_data(
    outcome: AgentTurnOutcome,
    tool_name: str,
) -> list[dict[str, Any]]:
    return [
        call.result["data"]
        for call in outcome.tool_calls
        if call.tool_name == tool_name
    ]


def _check_equal(
    *,
    path: str,
    expected: Any,
    observed: Any,
    issues: list[FixedQuestionIssue],
) -> None:
    _compare_subset(
        expected,
        observed,
        path=path,
        issues=issues,
    )


def validate_fixed_question_legacy(
    question_id: str,
    outcome: AgentTurnOutcome,
) -> LegacyFixedQuestionValidationResult:
    questions = load_frozen_questions()
    if question_id not in questions:
        raise ValueError(f"未知固定问题：{question_id}")
    question = questions[question_id]
    expected = question["reference_answer"]
    issues: list[FixedQuestionIssue] = []
    checks = [
        "问题类型与Agent终态一致",
        "工具调用顺序和数量符合冻结问题",
        "工具结构化结果与H2固定答案逐字段一致",
        "分析报告通过当前轮FACT确定性校验",
        "没有输出原始CustomerID或原始交易行",
    ]
    manual: list[str] = []

    if question_id in {f"Q{index:02d}" for index in range(1, 8)}:
        if outcome.status != "completed":
            issues.append(
                FixedQuestionIssue(
                    path="outcome.status",
                    expected='"completed"',
                    observed=_stable(outcome.status),
                )
            )
        rejected = getattr(outcome, "rejected_report_evidence", None)
        effective_report_validation = outcome.report_validation
        if effective_report_validation is None and rejected is not None:
            effective_report_validation = rejected.report_validation
        if (
            effective_report_validation is None
            or effective_report_validation.status != "passed"
        ):
            issues.append(
                FixedQuestionIssue(
                    path="report_validation.status",
                    expected='"passed"',
                    observed=_stable(
                        None
                        if effective_report_validation is None
                        else effective_report_validation.status
                    ),
                )
            )
        elif not effective_report_validation.referenced_fact_ids:
            issues.append(
                FixedQuestionIssue(
                    path="report_validation.referenced_fact_ids",
                    expected='"at least one current-turn FACT"',
                    observed="[]",
                )
            )

    expected_tools = {
        "Q01": ["get_sales_overview"],
        "Q02": ["rank_products"],
        "Q03": ["analyze_regions"],
        "Q04": ["analyze_time_trend"],
        "Q05": ["get_sales_overview", "compare_segments"],
        "Q06": ["analyze_time_trend", "rank_products"],
        "Q07": ["get_sales_overview", "analyze_customers"],
        "Q08": [],
        "Q09": [],
        "Q10": [],
    }[question_id]
    observed_tools = [call.tool_name for call in outcome.tool_calls]
    _check_equal(
        path="tool_calls",
        expected=expected_tools,
        observed=observed_tools,
        issues=issues,
    )

    for call_index, call in enumerate(outcome.tool_calls):
        privacy = call.result.get("privacy", {})
        if privacy.get("customer_id_values_exported") is not False:
            issues.append(
                FixedQuestionIssue(
                    path=(
                        f"tool_calls[{call_index}].result.privacy."
                        "customer_id_values_exported"
                    ),
                    expected="false",
                    observed=_stable(
                        privacy.get("customer_id_values_exported")
                    ),
                )
            )

    if question_id == "Q01" and _call_data(
        outcome, "get_sales_overview"
    ):
        _check_equal(
            path="reference_answer",
            expected=expected,
            observed=_call_data(
                outcome, "get_sales_overview"
            )[0],
            issues=issues,
        )
    elif question_id == "Q02" and _call_data(
        outcome, "rank_products"
    ):
        _check_equal(
            path="reference_answer",
            expected=expected,
            observed=_call_data(outcome, "rank_products")[0],
            issues=issues,
        )
    elif question_id == "Q03" and _call_data(
        outcome, "analyze_regions"
    ):
        _check_equal(
            path="reference_answer",
            expected=expected,
            observed=_call_data(outcome, "analyze_regions")[0],
            issues=issues,
        )
    elif question_id == "Q04" and _call_data(
        outcome, "analyze_time_trend"
    ):
        trend = _call_data(outcome, "analyze_time_trend")[0]
        observed = {
            "metric": trend["metric"],
            "excluded_incomplete_period": (
                trend["excluded_incomplete_periods"][0]
            ),
            "peak_complete_month": trend["peak_period"],
            "peak_month_metrics": trend["peak_period_metrics"],
        }
        _check_equal(
            path="reference_answer",
            expected=expected,
            observed=observed,
            issues=issues,
        )
    elif question_id == "Q05":
        segment = _call_data(outcome, "compare_segments")
        if segment:
            _check_equal(
                path="reference_answer",
                expected=expected,
                observed=segment[0],
                issues=issues,
            )
    elif question_id == "Q06":
        trends = _call_data(outcome, "analyze_time_trend")
        rankings = _call_data(outcome, "rank_products")
        if trends and rankings:
            trend = trends[0]
            peak = trend["peak_period"]
            observed = {
                "peak_complete_month": peak,
                "peak_month_metrics": trend[
                    "peak_period_metrics"
                ],
                "top_3_products_in_peak_month": rankings[0][
                    "ranking"
                ],
            }
            _check_equal(
                path="reference_answer",
                expected=expected,
                observed=observed,
                issues=issues,
            )
            year, month = map(int, peak.split("-"))
            last_day = calendar.monthrange(year, month)[1]
            expected_range = {
                "period": "custom",
                "start_date": f"{peak}-01",
                "end_date": f"{peak}-{last_day:02d}",
            }
            _check_equal(
                path="tool_calls[1].arguments.derived_period",
                expected=expected_range,
                observed={
                    key: outcome.tool_calls[1].arguments.get(key)
                    for key in expected_range
                },
                issues=issues,
            )
    elif question_id == "Q07":
        overviews = _call_data(outcome, "get_sales_overview")
        customers = _call_data(outcome, "analyze_customers")
        if overviews and customers:
            observed = {
                "overall": overviews[0],
                "known_customer_subset": customers[0],
                "privacy_note": customers[0].get("privacy_note"),
            }
            _check_equal(
                path="reference_answer",
                expected=expected,
                observed=observed,
                issues=issues,
            )
    elif question_id == "Q08":
        if outcome.status != "needs_clarification":
            issues.append(
                FixedQuestionIssue(
                    path="outcome.status",
                    expected='"needs_clarification"',
                    observed=_stable(outcome.status),
                )
            )
        observed_topics = (
            []
            if outcome.clarification is None
            else outcome.clarification.topics
        )
        _check_equal(
            path="clarification.topics",
            expected=expected["required_clarification_topics"],
            observed=observed_topics,
            issues=issues,
        )
    elif question_id == "Q09":
        if outcome.status != "boundary":
            issues.append(
                FixedQuestionIssue(
                    path="outcome.status",
                    expected='"boundary"',
                    observed=_stable(outcome.status),
                )
            )
        observed_fields = (
            []
            if outcome.boundary is None
            else outcome.boundary.missing_fields
        )
        _check_equal(
            path="boundary.missing_fields",
            expected=expected["missing_fields"],
            observed=observed_fields,
            issues=issues,
        )
        manual.append(
            "人工确认拒答没有把销售额冒充利润，且替代方案仅为销售额或销量排名。"
        )
    elif question_id == "Q10":
        if outcome.status != "boundary":
            issues.append(
                FixedQuestionIssue(
                    path="outcome.status",
                    expected='"boundary"',
                    observed=_stable(outcome.status),
                )
            )
        manual.append(
            "人工确认同时拒绝预测与自动补货，并仅建议查看带不完整期间提示的历史趋势。"
        )

    return LegacyFixedQuestionValidationResult(
        schema_version=(
            "1.5.6-h3-fixed-question-validation-v1"
        ),
        question_id=question_id,
        status="failed" if issues else "passed",
        deterministic_checks=checks,
        issues=issues,
        manual_review_items=manual,
    )


REQUEST_PATHS = {
    "Q02": {
        "metric": "metric",
        "top_n": "top_n",
    },
    "Q03": {
        "metric": "metric",
        "excluded_country": "excluded_country",
        "top_n": "top_n",
    },
    "Q04": {
        "metric": "metric",
        "excluded_incomplete_period": "excluded_period",
    },
    "Q06": {"$request": "top_n"},
}
REQUEST_DISPLAY_ALIASES = {
    "sales_amount_gbp": ("销售额", "销售金额"),
    "sales_quantity_items": ("销量", "销售数量"),
    "order_count": ("订单数",),
    "average_order_value_gbp": ("客单价", "平均订单金额"),
}
POLICY_PATHS = {
    "Q07": {"privacy_note": "aggregate_customer_privacy"},
}
FACT_METRIC_BY_KEY = {
    "sales_amount_gbp": "sales_amount",
    "sales_quantity_items": "sales_quantity",
    "order_count": "order_count",
    "average_order_value_gbp": "average_order_value",
    "customer_count": "customer_count",
    "sales_row_coverage": "sales_row_coverage",
    "sales_amount_coverage": "sales_amount_coverage",
    "united_kingdom_sales_amount_share": "sales_amount_share",
    "outside_united_kingdom_sales_amount_share": "sales_amount_share",
    "time_minimum": "time_minimum",
    "time_maximum": "time_maximum",
    "incomplete_period_warning": "incomplete_period",
    "peak_complete_month": "peak_period",
}


def _flatten_leaves(
    value: Any,
    path: str = "",
) -> list[tuple[str, Any]]:
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


def _claim_references(
    outcome: AgentTurnOutcome,
) -> list[tuple[str, Any]]:
    report_draft = outcome.report_draft
    if report_draft is None:
        rejected = getattr(outcome, "rejected_report_evidence", None)
        if rejected is not None:
            report_draft = rejected.report_draft
    if report_draft is None:
        return []
    return [
        (claim.statement, reference)
        for section in report_draft.sections
        for claim in section.claims
        for reference in claim.evidence
    ]


def _statement_contains(statement: str, value: Any) -> bool:
    expected_tokens = canonical_numeric_tokens(str(value))
    if expected_tokens:
        return bool(expected_tokens & canonical_numeric_tokens(statement))
    return str(value).casefold() in statement.casefold()


def _request_statement_contains(statement: str, value: Any) -> bool:
    text = statement.casefold()
    internal = str(value).casefold()
    if internal in text:
        return True
    return any(
        alias.casefold() in text
        for alias in REQUEST_DISPLAY_ALIASES.get(str(value), ())
    )


def _diagnostic_request_records(
    outcome: AgentTurnOutcome,
) -> tuple[RequestRecord, ...]:
    if outcome.request_records:
        return outcome.request_records
    rejected = getattr(outcome, "rejected_report_evidence", None)
    return () if rejected is None else rejected.request_records


def _diagnostic_policy_records(
    outcome: AgentTurnOutcome,
) -> tuple[PolicyRecord, ...]:
    if outcome.policy_records:
        return outcome.policy_records
    rejected = getattr(outcome, "rejected_report_evidence", None)
    return () if rejected is None else rejected.policy_records


def _dimensions(fact: FactRecord) -> dict[str, str]:
    return {item.name: item.value for item in fact.dimensions}


def _ranking_context(
    reference_answer: dict[str, Any],
    path: str,
) -> tuple[int | None, dict[str, str]]:
    match = re.search(
        r"(?P<name>ranking|top_3_products_in_peak_month)\[(?P<index>\d+)\]",
        path,
    )
    if match is None:
        return None, {}
    rows = reference_answer[match.group("name")]
    row = rows[int(match.group("index"))]
    expected_dimensions = {
        key: str(row[key])
        for key in ("stock_code", "product_name", "country")
        if key in row
    }
    return int(match.group("index")) + 1, expected_dimensions


def _segment_context(path: str) -> str | None:
    if path.startswith("united_kingdom.") or path.startswith(
        "united_kingdom_sales_amount_share"
    ):
        return "united_kingdom"
    if path.startswith("outside_united_kingdom.") or path.startswith(
        "outside_united_kingdom_sales_amount_share"
    ):
        return "outside_united_kingdom"
    if path.startswith("known_customer_subset."):
        return "known_customer_subset"
    if path.startswith("overall."):
        return "overall"
    return None


def _fact_matches_manifest_item(
    *,
    fact: FactRecord,
    path: str,
    expected_value: Any,
    reference_answer: dict[str, Any],
) -> bool:
    key = path.rsplit(".", 1)[-1]
    dimensions = _dimensions(fact)
    rank, expected_dimensions = _ranking_context(
        reference_answer,
        path,
    )
    if rank is not None and any(
        dimensions.get(name) != value
        for name, value in expected_dimensions.items()
    ):
        return False
    segment = _segment_context(path)
    if segment is not None:
        observed_segment = dimensions.get("segment")
        if segment == "overall":
            if observed_segment not in {None, "overall"}:
                return False
        elif observed_segment != segment:
            return False
    if key in {"stock_code", "product_name", "country", "month"}:
        dimension_name = key
        return dimensions.get(dimension_name) == str(expected_value)
    metric = FACT_METRIC_BY_KEY.get(key)
    if metric is None and key == "excluded_incomplete_period":
        metric = "incomplete_period"
    if metric is None:
        return False
    if fact.metric != metric or fact.value != str(expected_value):
        return False
    if rank is not None and metric == "sales_amount":
        return fact.rank == rank
    return True


def _manifest_item(
    *,
    question_id: str,
    path: str,
    expected_value: Any,
    outcome: AgentTurnOutcome,
    reference_answer: dict[str, Any],
) -> EvidenceManifestItem:
    top_level = path.split(".", 1)[0]
    source_type: Literal["FACT", "REQUEST", "POLICY"] = "FACT"
    parameter_name = REQUEST_PATHS.get(question_id, {}).get(top_level)
    policy_code = POLICY_PATHS.get(question_id, {}).get(top_level)
    if parameter_name is not None:
        source_type = "REQUEST"
    elif policy_code is not None:
        source_type = "POLICY"

    facts = {fact.fact_id: fact for fact in outcome.facts}
    requests = {
        item.request_id: item
        for item in _diagnostic_request_records(outcome)
    }
    policies = {
        item.policy_id: item
        for item in _diagnostic_policy_records(outcome)
    }
    evidence_ids: list[str] = []
    for statement, reference in _claim_references(outcome):
        if source_type == "REQUEST":
            if not isinstance(reference, ReportRequestReference):
                continue
            record = requests.get(reference.request_id)
            if (
                record is not None
                and record.parameter_name == parameter_name
                and record.value == str(expected_value)
                and _request_statement_contains(
                    statement, expected_value
                )
            ):
                evidence_ids.append(reference.request_id)
            continue
        if not _statement_contains(statement, expected_value):
            continue
        if source_type == "FACT" and isinstance(
            reference,
            ReportFactReference,
        ):
            fact = facts.get(reference.fact_id)
            if fact is not None and _fact_matches_manifest_item(
                fact=fact,
                path=path,
                expected_value=expected_value,
                reference_answer=reference_answer,
            ):
                evidence_ids.append(reference.fact_id)
        elif source_type == "POLICY" and isinstance(
            reference,
            ReportPolicyReference,
        ):
            record = policies.get(reference.policy_id)
            if (
                record is not None
                and record.code == policy_code
                and record.message == str(expected_value)
            ):
                evidence_ids.append(reference.policy_id)
    return EvidenceManifestItem(
        path=path,
        source_type=source_type,
        expected=_stable(expected_value),
        covered=bool(evidence_ids),
        evidence_ids=list(dict.fromkeys(evidence_ids)),
    )


def _content_manifest(
    question_id: str,
    outcome: AgentTurnOutcome,
    reference_answer: dict[str, Any],
) -> list[EvidenceManifestItem]:
    items = [
        _manifest_item(
            question_id=question_id,
            path=path,
            expected_value=value,
            outcome=outcome,
            reference_answer=reference_answer,
        )
        for path, value in _flatten_leaves(reference_answer)
    ]
    if question_id == "Q06":
        items.append(
            _manifest_item(
                question_id="Q06",
                path="$request.top_n",
                expected_value="3",
                outcome=outcome,
                reference_answer=reference_answer,
            )
        )
    return items


def _control_content_issues(
    question_id: str,
    outcome: AgentTurnOutcome,
    expected: dict[str, Any],
) -> list[FixedQuestionIssue]:
    issues: list[FixedQuestionIssue] = []
    if question_id == "Q08":
        if outcome.model_response_count != 1:
            issues.append(
                FixedQuestionIssue(
                    path="clarification.response_count",
                    expected="1",
                    observed=_stable(outcome.model_response_count),
                )
            )
    elif question_id == "Q09" and outcome.boundary is not None:
        _check_equal(
            path="boundary.supported_alternative",
            expected=expected["supported_alternative"],
            observed=outcome.boundary.supported_alternative,
            issues=issues,
        )
        combined = (
            outcome.boundary.message
            + " "
            + outcome.boundary.supported_alternative
        )
        if re.search(r"(?:利润|利润率).{0,12}\d|\d.{0,12}(?:利润|利润率)", combined):
            issues.append(
                FixedQuestionIssue(
                    path="boundary.unsupported_profit_number",
                    expected="no profit or profit-rate number",
                    observed=_stable(combined),
                )
            )
    elif question_id == "Q10" and outcome.boundary is not None:
        _check_equal(
            path="boundary.supported_alternative",
            expected=expected["supported_alternative"],
            observed=outcome.boundary.supported_alternative,
            issues=issues,
        )
        _check_equal(
            path="boundary.boundary_codes",
            expected=[
                "forecasting_unsupported",
                "automatic_replenishment_unsupported",
            ],
            observed=outcome.boundary.boundary_codes,
            issues=issues,
        )
        combined = (
            outcome.boundary.message
            + " "
            + outcome.boundary.supported_alternative
        )
        if re.search(r"(?:可以|将|会|建议|应).{0,12}(?:预测|自动补货)", combined):
            issues.append(
                FixedQuestionIssue(
                    path="boundary.contradictory_capability_promise",
                    expected="no forecast or automatic replenishment promise",
                    observed=_stable(combined),
                )
            )
        forbidden_numbers = canonical_numeric_tokens(
            outcome.boundary.message
        )
        if forbidden_numbers:
            issues.append(
                FixedQuestionIssue(
                    path="boundary.forecast_or_action_numbers",
                    expected="no forecast or replenishment numbers",
                    observed=_stable(sorted(forbidden_numbers)),
                )
            )
    return issues


def validate_fixed_question(
    question_id: str,
    outcome: AgentTurnOutcome,
) -> FixedQuestionValidationResult | LegacyFixedQuestionValidationResult:
    if not hasattr(outcome, "request_records"):
        return validate_fixed_question_legacy(question_id, outcome)
    questions = load_frozen_questions()
    question = questions[question_id]
    legacy = validate_fixed_question_legacy(question_id, outcome)
    issues = list(legacy.issues)
    manifest: list[EvidenceManifestItem] = []
    report_questions = {f"Q{index:02d}" for index in range(1, 8)}
    rejected = getattr(outcome, "rejected_report_evidence", None)
    upstream_report_failure = (
        question_id in report_questions
        and outcome.status == "failed"
        and outcome.error_stage == "report_validation"
        and rejected is not None
        and rejected.report_validation.status == "failed"
    )
    terminal_output_truncation = (
        question_id in report_questions
        and outcome.status == "failed"
        and outcome.error_stage == "model_response"
        and provider_output_was_truncated(outcome.raw_responses)
    )
    if terminal_output_truncation:
        issues = [
            item
            for item in issues
            if item.path == "outcome.status"
            or item.path.startswith("reference_answer")
        ]
        issues.append(
            FixedQuestionIssue(
                path="terminal.finish_reason",
                expected=_stable("stop"),
                observed=_stable("length"),
            )
        )
    elif question_id in report_questions:
        manifest = _content_manifest(
            question_id,
            outcome,
            question["reference_answer"],
        )
        if not upstream_report_failure:
            issues.extend(
                FixedQuestionIssue(
                    path=f"report_completeness.{item.path}",
                    expected=item.expected,
                    observed="<missing evidence-backed claim>",
                )
                for item in manifest
                if not item.covered
            )
    else:
        issues.extend(
            _control_content_issues(
                question_id,
                outcome,
                question["reference_answer"],
            )
        )

    tool_issues = [
        item for item in legacy.issues if item.path.startswith("reference_answer")
    ]
    dataflow_issues = [
        item
        for item in legacy.issues
        if not item.path.startswith("reference_answer")
    ]
    content_issues = [
        item
        for item in issues
        if item.path.startswith("report_completeness.")
        or item.path.startswith("clarification.")
        or item.path.startswith("boundary.supported_alternative")
        or item.path.startswith("boundary.boundary_codes")
        or item.path.startswith("boundary.unsupported_")
        or item.path.startswith("boundary.contradictory_")
        or item.path.startswith("boundary.forecast_")
    ]
    protocol_mock_status: Literal["passed", "not_applicable"] = (
        "passed"
        if outcome.raw_responses
        and all(item.get("offline_mock") for item in outcome.raw_responses)
        else "not_applicable"
    )
    dataflow_status = "failed" if dataflow_issues else "passed"
    if question_id in {"Q08", "Q09", "Q10"}:
        tool_status = "not_applicable"
    else:
        tool_status = "failed" if tool_issues else "passed"
    if terminal_output_truncation:
        content_status = "not_evaluated_due_to_terminal_output_truncation"
    elif upstream_report_failure:
        content_status = (
            "not_evaluated_due_to_upstream_report_validation_failure"
        )
    else:
        content_status = "failed" if content_issues else "passed"
    if issues:
        if (
            dataflow_status == "passed"
            and tool_status in {"passed", "not_applicable"}
            and content_status == "failed"
        ):
            status = "protocol_and_dataflow_passed"
        else:
            status = "failed"
    else:
        status = "passed_deterministic_pending_manual_review"
    return FixedQuestionValidationResult(
        schema_version="1.5.6-h3-fixed-question-validation-v2",
        question_id=question_id,
        status=status,
        protocol_mock_status=protocol_mock_status,
        dataflow_mock_status=dataflow_status,
        tool_reference_answer_status=tool_status,
        report_content_acceptance_status=content_status,
        manual_review_status="pending",
        real_model_validation_status="current_model_real_status_unknown",
        deterministic_checks=legacy.deterministic_checks
        + [
            "Q01至Q07逐项内容必须由FACT、REQUEST或POLICY支持",
            "Q08至Q10控制终态内容满足冻结边界",
            "自动通过与人工待审、真实模型状态分开记录",
        ],
        issues=issues,
        evidence_manifest=manifest,
        manual_review_items=list(question["manual_checklist"]),
    )
