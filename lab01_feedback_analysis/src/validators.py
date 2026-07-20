from __future__ import annotations

from dataclasses import dataclass

from src.schemas import (
    FeedbackAnalysis,
    SentimentLabel,
)


@dataclass(frozen=True)
class ValidationIssue:
    """程序校验发现的一个问题。"""

    code: str
    field_path: str
    message: str


PUNCTUATION_TRANSLATION = str.maketrans(
    {
        "，": ",",
        "。": ".",
        "！": "!",
        "？": "?",
        "：": ":",
        "；": ";",
        "（": "(",
        "）": ")",
    }
)


def normalize_punctuation(text: str) -> str:
    """
    仅用于诊断全角、半角标点差异。

    该结果不能代替原文证据校验。
    """
    return text.translate(
        PUNCTUATION_TRANSLATION
    )


def validate_review_id(
    result: FeedbackAnalysis,
    expected_review_id: str,
) -> list[ValidationIssue]:
    """检查模型返回的 ID 是否与输入完全一致。"""
    if result.review_id == expected_review_id:
        return []

    return [
        ValidationIssue(
            code="review_id_mismatch",
            field_path="review_id",
            message=(
                "模型返回的 review_id 与输入不一致："
                f"输入为 {expected_review_id!r}，"
                f"输出为 {result.review_id!r}"
            ),
        )
    ]


def validate_evidence(
    result: FeedbackAnalysis,
    review_text: str,
) -> list[ValidationIssue]:
    """检查每条 evidence 是否为评论中的连续原文片段。"""
    issues: list[ValidationIssue] = []

    normalized_review = normalize_punctuation(
        review_text
    )

    for index, aspect in enumerate(result.aspects):
        evidence = aspect.evidence
        field_path = f"aspects[{index}].evidence"

        if evidence in review_text:
            continue

        normalized_evidence = normalize_punctuation(
            evidence
        )

        if normalized_evidence in normalized_review:
            issues.append(
                ValidationIssue(
                    code="evidence_punctuation_mismatch",
                    field_path=field_path,
                    message=(
                        f"{aspect.aspect.value} 维度的证据"
                        "仅在转换全角、半角标点后匹配。"
                        "按照本实验规则仍判定为失败，"
                        "模型必须返回原始连续文本。"
                    ),
                )
            )
        else:
            issues.append(
                ValidationIssue(
                    code="evidence_not_found",
                    field_path=field_path,
                    message=(
                        f"{aspect.aspect.value} 维度的证据"
                        "不是评论中的连续原文片段："
                        f"{evidence!r}"
                    ),
                )
            )

    return issues


def validate_duplicate_aspects(
    result: FeedbackAnalysis,
) -> list[ValidationIssue]:
    """
    防御性检查重复维度。

    Pydantic Schema 已经检查一次，这里保留是为了
    后续批量流程能够统一返回结构化错误。
    """
    aspect_names = [
        aspect.aspect.value
        for aspect in result.aspects
    ]

    duplicate_names = sorted(
        {
            name
            for name in aspect_names
            if aspect_names.count(name) > 1
        }
    )

    if not duplicate_names:
        return []

    return [
        ValidationIssue(
            code="duplicate_aspects",
            field_path="aspects",
            message=(
                "存在重复评价维度："
                + ", ".join(duplicate_names)
            ),
        )
    ]


def validate_issue_consistency(
    result: FeedbackAnalysis,
) -> list[ValidationIssue]:
    """补充检查问题、建议和维度情感是否一致。"""
    issues: list[ValidationIssue] = []

    issue_aspects = [
        aspect
        for aspect in result.aspects
        if aspect.sentiment in {
            SentimentLabel.NEGATIVE,
            SentimentLabel.MIXED,
        }
    ]

    if result.issue_summary and not issue_aspects:
        issues.append(
            ValidationIssue(
                code="unsupported_issue_summary",
                field_path="issue_summary",
                message=(
                    "问题概括没有 negative 或 mixed "
                    "评价维度作为依据"
                ),
            )
        )

    if result.suggested_action and not result.issue_summary:
        issues.append(
            ValidationIssue(
                code="unsupported_suggested_action",
                field_path="suggested_action",
                message=(
                    "没有识别出问题时，不应生成改进建议"
                ),
            )
        )

    return issues


def validate_analysis_output(
    result: FeedbackAnalysis,
    expected_review_id: str,
    review_text: str,
) -> list[ValidationIssue]:
    """运行一条模型输出的全部程序校验。"""
    issues: list[ValidationIssue] = []

    issues.extend(
        validate_review_id(
            result=result,
            expected_review_id=expected_review_id,
        )
    )

    issues.extend(
        validate_evidence(
            result=result,
            review_text=review_text,
        )
    )

    issues.extend(
        validate_duplicate_aspects(result)
    )

    issues.extend(
        validate_issue_consistency(result)
    )

    return issues