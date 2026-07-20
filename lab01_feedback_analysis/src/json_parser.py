from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from src.schemas import FeedbackAnalysis


class JSONOutputError(ValueError):
    """模型返回内容不是合法 JSON 时抛出的异常。"""


CODE_FENCE_PATTERN = re.compile(
    r"^```(?:json)?\s*(\{.*\})\s*```$",
    flags=re.IGNORECASE | re.DOTALL,
)


def remove_json_code_fence(text: str) -> str:
    """
    移除完整包围 JSON 的 Markdown 代码围栏。

    只用于错误恢复，不接受 JSON 前后的其他说明文字。
    """
    match = CODE_FENCE_PATTERN.fullmatch(text.strip())

    if match is None:
        raise JSONOutputError(
            "模型返回了无法安全移除的 Markdown 代码围栏"
        )

    return match.group(1).strip()


def parse_json_object(
    raw_text: str,
    *,
    allow_code_fence: bool = False,
) -> dict[str, Any]:
    """把模型原始文本严格解析为 JSON 对象。"""
    if not isinstance(raw_text, str):
        raise JSONOutputError(
            "模型返回内容必须是字符串"
        )

    text = raw_text.strip()

    if not text:
        raise JSONOutputError(
            "模型返回内容为空"
        )

    if text.startswith("```"):
        if not allow_code_fence:
            raise JSONOutputError(
                "模型返回了 Markdown 代码围栏"
            )

        text = remove_json_code_fence(text)

    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise JSONOutputError(
            "模型返回内容不是合法 JSON："
            f"第 {error.lineno} 行，"
            f"第 {error.colno} 列，"
            f"{error.msg}"
        ) from error

    if not isinstance(data, dict):
        raise JSONOutputError(
            "模型返回的 JSON 顶层必须是对象"
        )

    return data


def parse_feedback_analysis(
    raw_text: str,
    *,
    allow_code_fence: bool = False,
) -> FeedbackAnalysis:
    """
    将模型返回内容解析并转换为 FeedbackAnalysis。

    JSON 语法错误由 JSONOutputError 表示；
    字段和业务结构错误由 Pydantic ValidationError 表示。
    """
    data = parse_json_object(
        raw_text,
        allow_code_fence=allow_code_fence,
    )

    return FeedbackAnalysis.model_validate(data)


def format_validation_error(
    error: ValidationError,
) -> list[dict[str, str]]:
    """把 Pydantic 错误转换为便于展示和记录的结构。"""
    formatted_errors: list[dict[str, str]] = []

    for item in error.errors(
        include_url=False,
        include_context=False,
        include_input=False,
    ):
        location = ".".join(
            str(part)
            for part in item["loc"]
        )

        formatted_errors.append(
            {
                "code": f"schema_{item['type']}",
                "field_path": location,
                "error_type": item["type"],
                "message": item["msg"],
            }
        )

    return formatted_errors