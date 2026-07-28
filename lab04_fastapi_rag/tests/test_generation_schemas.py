from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.generation_schemas import (
    parse_classification,
    parse_rag_answer,
    validate_answer_markdown,
    validate_citations,
)


def test_parses_exact_answer_and_refusal_schemas() -> None:
    answered = parse_rag_answer(
        '{"answerable":true,"answer":"使用 `HTTPException`。",'
        '"cited_chunk_ids":["chunk_1"],"refusal_reason":null}'
    )
    refused = parse_rag_answer(
        '{"answerable":false,"answer":null,"cited_chunk_ids":[],'
        '"refusal_reason":"证据不足"}'
    )

    assert answered.answerable is True
    assert refused.answerable is False


@pytest.mark.parametrize(
    "content",
    [
        '前缀{"question_type":"procedure"}',
        '{"question_type":"procedure","extra":1}',
        '{"question_type":"unknown"}',
        '["procedure"]',
    ],
)
def test_classification_rejects_non_schema_content(content: str) -> None:
    with pytest.raises((ValueError, ValidationError)):
        parse_classification(content)


def test_answer_state_rules_and_citation_set_are_program_checked() -> None:
    with pytest.raises((ValueError, ValidationError), match="至少需要一个引用"):
        parse_rag_answer(
            '{"answerable":true,"answer":"内容",'
            '"cited_chunk_ids":[],"refusal_reason":null}'
        )
    answer = parse_rag_answer(
        '{"answerable":true,"answer":"内容",'
        '"cited_chunk_ids":["outside"],"refusal_reason":null}'
    )
    with pytest.raises(ValueError, match="证据之外"):
        validate_citations(answer, {"inside"})


@pytest.mark.parametrize(
    "answer",
    [
        "<b>不安全</b>",
        "参见 https://example.com",
        "| A | B |\n| --- | --- |\n| 1 | 2 |",
        "结论见[1]。",
    ],
)
def test_markdown_safety_rejects_forbidden_content(answer: str) -> None:
    with pytest.raises(ValueError):
        validate_answer_markdown(answer)


def test_python_syntax_is_warning_not_validation_failure() -> None:
    warnings = validate_answer_markdown(
        "示例：\n```python\nif True print('x')\n```"
    )

    assert len(warnings) == 1
    assert "语法检查失败" in warnings[0]
