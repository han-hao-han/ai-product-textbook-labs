from __future__ import annotations

from typing import Any

from src.schemas import FeedbackAnalysis
from src.validators import ValidationIssue


def contains_any_keyword(
    text: str,
    keywords: list[str],
) -> bool:
    """判断文本是否包含至少一个目标关键词。"""
    return any(
        keyword in text
        for keyword in keywords
    )


def validate_semantic_expectation(
    result: FeedbackAnalysis,
    expectation: dict[str, Any],
) -> list[ValidationIssue]:
    """
    根据人工定义的语义预期检查模型输出。

    该检查只用于固定演示集和回归测试，
    不用于任意未知用户评论。
    """
    issues: list[ValidationIssue] = []

    accepted_overall = expectation.get(
        "accepted_overall_sentiments",
        [],
    )

    if (
        accepted_overall
        and result.overall_sentiment.value
        not in accepted_overall
    ):
        issues.append(
            ValidationIssue(
                code="unexpected_overall_sentiment",
                field_path="overall_sentiment",
                message=(
                    "总体情感不符合人工预期："
                    f"实际为 "
                    f"{result.overall_sentiment.value!r}，"
                    f"允许值为 {accepted_overall}"
                ),
            )
        )

    predicted_aspects = {
        aspect.aspect.value: aspect
        for aspect in result.aspects
    }

    required_aspects = expectation.get(
        "required_aspects",
        {},
    )

    for aspect_name, accepted_sentiments in (
        required_aspects.items()
    ):
        predicted = predicted_aspects.get(
            aspect_name
        )

        if predicted is None:
            issues.append(
                ValidationIssue(
                    code="required_aspect_missing",
                    field_path="aspects",
                    message=(
                        f"缺少必须识别的维度："
                        f"{aspect_name}"
                    ),
                )
            )
            continue

        actual_sentiment = (
            predicted.sentiment.value
        )

        if actual_sentiment not in accepted_sentiments:
            issues.append(
                ValidationIssue(
                    code="unexpected_aspect_sentiment",
                    field_path=(
                        f"aspects.{aspect_name}"
                        ".sentiment"
                    ),
                    message=(
                        f"{aspect_name} 维度情感"
                        "不符合人工预期："
                        f"实际为 {actual_sentiment!r}，"
                        f"允许值为 "
                        f"{accepted_sentiments}"
                    ),
                )
            )

    evidence_expectations = expectation.get(
        "aspect_evidence_keywords_any",
        {},
    )

    for aspect_name, keywords in (
        evidence_expectations.items()
    ):
        predicted = predicted_aspects.get(
            aspect_name
        )

        if predicted is None:
            continue

        if not contains_any_keyword(
            predicted.evidence,
            keywords,
        ):
            issues.append(
                ValidationIssue(
                    code="expected_evidence_missing",
                    field_path=(
                        f"aspects.{aspect_name}"
                        ".evidence"
                    ),
                    message=(
                        f"{aspect_name} 维度证据"
                        "没有覆盖人工确认的重要内容。"
                        f"至少应包含一个关键词："
                        f"{keywords}"
                    ),
                )
            )

    if (
        expectation.get(
            "issue_summary_required",
            False,
        )
        and not result.issue_summary
    ):
        issues.append(
            ValidationIssue(
                code="issue_summary_missing",
                field_path="issue_summary",
                message=(
                    "人工确认评论中存在问题或"
                    "改进诉求，但模型未输出问题概括"
                ),
            )
        )

    if (
        expectation.get(
            "suggested_action_required",
            False,
        )
        and not result.suggested_action
    ):
        issues.append(
            ValidationIssue(
                code="suggested_action_missing",
                field_path="suggested_action",
                message=(
                    "人工确认评论中存在改进诉求，"
                    "但模型未输出改进建议"
                ),
            )
        )

    issue_keywords = expectation.get(
        "issue_keywords_any",
        [],
    )

    if (
        issue_keywords
        and result.issue_summary
        and not contains_any_keyword(
            result.issue_summary,
            issue_keywords,
        )
    ):
        issues.append(
            ValidationIssue(
                code="expected_issue_content_missing",
                field_path="issue_summary",
                message=(
                    "问题概括没有覆盖人工确认的"
                    "核心改进诉求。"
                    f"至少应包含一个关键词："
                    f"{issue_keywords}"
                ),
            )
        )

    return issues