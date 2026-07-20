from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class SentimentLabel(str, Enum):
    """评论或评价维度的情感标签。"""

    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    MIXED = "mixed"


class AspectName(str, Enum):
    """教材实验使用的五个粗粒度评价维度。"""

    LOCATION = "location"
    SERVICE = "service"
    PRICE = "price"
    ENVIRONMENT = "environment"
    FOOD = "food"


QUOTE_PAIRS = {
    '"': '"',
    "'": "'",
    "“": "”",
    "‘": "’",
    "「": "」",
    "『": "』",
}


class AspectAnalysis(BaseModel):
    """单个评价维度的分析结果。"""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    aspect: AspectName
    sentiment: SentimentLabel
    evidence: str = Field(
        min_length=1,
        max_length=500,
        description="评论中的连续原文片段",
    )

    @field_validator("evidence", mode="before")
    @classmethod
    def clean_evidence(cls, value: Any) -> Any:
        """
        去除模型可能额外添加的一层引号。

        这里只移除最外层引号，不改写标点或原文内容。
        """
        if not isinstance(value, str):
            return value

        cleaned = value.strip()

        if len(cleaned) >= 2:
            first_character = cleaned[0]
            expected_last = QUOTE_PAIRS.get(first_character)

            if expected_last and cleaned[-1] == expected_last:
                cleaned = cleaned[1:-1].strip()

        return cleaned


class FeedbackAnalysis(BaseModel):
    """一条评论的完整结构化分析结果。"""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    review_id: str = Field(
        min_length=1,
        max_length=100,
        strict=True,
    )

    overall_sentiment: SentimentLabel

    aspects: list[AspectAnalysis] = Field(
        default_factory=list,
        max_length=5,
    )

    issue_summary: str = Field(
        default="",
        max_length=300,
    )

    suggested_action: str = Field(
        default="",
        max_length=300,
    )

    @field_validator(
        "issue_summary",
        "suggested_action",
        mode="before",
    )
    @classmethod
    def normalize_optional_text(cls, value: Any) -> Any:
        """允许模型用 null 表示没有问题或建议。"""
        if value is None:
            return ""

        return value

    @model_validator(mode="after")
    def validate_business_structure(self) -> "FeedbackAnalysis":
        """检查维度重复及问题、建议之间的基本关系。"""
        aspect_names = [
            aspect.aspect
            for aspect in self.aspects
        ]

        if len(aspect_names) != len(set(aspect_names)):
            raise ValueError(
                "aspects 中不能出现重复的评价维度"
            )

        issue_aspects = [
            aspect
            for aspect in self.aspects
            if aspect.sentiment in {
                SentimentLabel.NEGATIVE,
                SentimentLabel.MIXED,
            }
        ]

        if self.issue_summary and not issue_aspects:
            raise ValueError(
                "没有 negative 或 mixed 维度时，"
                "issue_summary 应为空字符串"
            )

        if self.issue_summary and not self.suggested_action:
            raise ValueError(
                "存在 issue_summary 时必须提供 suggested_action"
            )

        if self.suggested_action and not self.issue_summary:
            raise ValueError(
                "没有 issue_summary 时不能单独生成 suggested_action"
            )

        if not self.aspects:
            if self.overall_sentiment == SentimentLabel.MIXED:
                raise ValueError(
                    "aspects 为空时，overall_sentiment "
                    "不能为 mixed"
                )

        return self