from __future__ import annotations

import ast
import json
import re
from enum import Enum
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictStr,
    model_validator,
)


class QuestionType(str, Enum):
    concise_concept = "concise_concept"
    procedure = "procedure"
    code_example = "code_example"
    comprehensive = "comprehensive"


class QuestionClassification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_type: QuestionType


class RagAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answerable: StrictBool
    answer: StrictStr | None
    cited_chunk_ids: list[StrictStr] = Field(max_length=5)
    refusal_reason: StrictStr | None

    @model_validator(mode="after")
    def validate_state(self) -> "RagAnswer":
        if self.answerable:
            if not self.answer or not self.answer.strip():
                raise ValueError("answerable=true时answer必须是非空字符串")
            if not self.cited_chunk_ids:
                raise ValueError("answerable=true时至少需要一个引用")
            if self.refusal_reason is not None:
                raise ValueError("answerable=true时refusal_reason必须为null")
        else:
            if self.answer is not None:
                raise ValueError("answerable=false时answer必须为null")
            if self.cited_chunk_ids:
                raise ValueError("answerable=false时引用必须为空")
            if not self.refusal_reason or not self.refusal_reason.strip():
                raise ValueError("answerable=false时必须说明拒答原因")
        if len(set(self.cited_chunk_ids)) != len(self.cited_chunk_ids):
            raise ValueError("引用Chunk ID不得重复")
        return self


def _strict_json_object(content: str) -> dict[str, Any]:
    if not isinstance(content, str) or not content.strip():
        raise ValueError("结构化响应内容为空")
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as error:
        raise ValueError("结构化响应不是完整合法JSON") from error
    if not isinstance(payload, dict):
        raise ValueError("结构化响应顶层必须是JSON对象")
    return payload


def parse_classification(content: str) -> QuestionClassification:
    return QuestionClassification.model_validate(_strict_json_object(content))


def parse_rag_answer(content: str) -> RagAnswer:
    return RagAnswer.model_validate(_strict_json_object(content))


def validate_citations(
    answer: RagAnswer,
    allowed_chunk_ids: set[str],
) -> None:
    unknown = sorted(set(answer.cited_chunk_ids) - allowed_chunk_ids)
    if unknown:
        raise ValueError(f"回答引用了本次证据之外的Chunk：{unknown}")


HTML_PATTERN = re.compile(r"<\s*/?\s*[A-Za-z!][^>]*>")
EXTERNAL_LINK_PATTERN = re.compile(
    r"https?://|(?<!\!)\[[^\]]+\]\(\s*(?:https?://|//)",
    re.IGNORECASE,
)
TABLE_SEPARATOR_PATTERN = re.compile(
    r"^\s*\|?(?:\s*:?-{3,}:?\s*\|){1,}\s*:?-{3,}:?\s*\|?\s*$",
    re.MULTILINE,
)
SELF_CITATION_PATTERN = re.compile(
    r"(?:\[\s*(?:\d+|引用\s*\d+|来源\s*\d+)\s*\]|"
    r"【\s*(?:\d+|引用\s*\d+|来源\s*\d+)\s*】)"
)
PYTHON_BLOCK_PATTERN = re.compile(
    r"```(?:python|py)\s*\n(.*?)```",
    re.IGNORECASE | re.DOTALL,
)


def validate_answer_markdown(answer: str) -> list[str]:
    if HTML_PATTERN.search(answer):
        raise ValueError("回答包含禁止的HTML")
    if EXTERNAL_LINK_PATTERN.search(answer):
        raise ValueError("回答包含禁止的外部链接")
    if TABLE_SEPARATOR_PATTERN.search(answer):
        raise ValueError("回答包含禁止的Markdown表格")
    if SELF_CITATION_PATTERN.search(answer):
        raise ValueError("回答包含模型自制引用编号")
    warnings: list[str] = []
    for index, code in enumerate(PYTHON_BLOCK_PATTERN.findall(answer), start=1):
        try:
            ast.parse(code)
        except SyntaxError as error:
            warnings.append(
                f"第{index}个Python代码块语法检查失败："
                f"line={error.lineno}, message={error.msg}"
            )
    return warnings
