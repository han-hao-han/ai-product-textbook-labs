from __future__ import annotations

import json
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr


class AnswerGrade(str, Enum):
    fully_correct = "fully_correct"
    mostly_correct = "mostly_correct"
    incorrect = "incorrect"


class JudgeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer_grade: AnswerGrade
    covered_required_points: list[StrictStr]
    missing_required_points: list[StrictStr]
    critical_errors: list[StrictStr]
    unsupported_major_claim: StrictBool
    citation_supports_answer: StrictBool
    citation_set_minimal: StrictBool
    review_reason: StrictStr = Field(min_length=1, max_length=2000)


def parse_judge_output(
    content: str,
    *,
    required_points: tuple[str, ...],
    allowed_critical_errors: tuple[str, ...],
) -> JudgeOutput:
    try:
        raw: Any = json.loads(content)
    except json.JSONDecodeError as error:
        raise ValueError("Judge输出不是完整合法JSON") from error
    if not isinstance(raw, dict):
        raise ValueError("Judge输出顶层必须是JSON对象")
    result = JudgeOutput.model_validate(raw)

    covered = result.covered_required_points
    missing = result.missing_required_points
    if len(covered) != len(set(covered)) or len(missing) != len(set(missing)):
        raise ValueError("Judge必答点数组包含重复项")
    if set(covered) & set(missing):
        raise ValueError("Judge必答点不能同时标记为覆盖和缺失")
    if set(covered) | set(missing) != set(required_points):
        raise ValueError("Judge未按预冻结必答点原文完成精确划分")
    if len(result.critical_errors) != len(set(result.critical_errors)):
        raise ValueError("Judge关键错误数组包含重复项")
    if not set(result.critical_errors) <= set(allowed_critical_errors):
        raise ValueError("Judge返回了预冻结范围之外的关键错误")
    if result.answer_grade is AnswerGrade.fully_correct:
        if (
            missing
            or result.critical_errors
            or result.unsupported_major_claim
            or not result.citation_supports_answer
        ):
            raise ValueError("fully_correct与缺失点、关键错误或引用判断矛盾")
    return result
