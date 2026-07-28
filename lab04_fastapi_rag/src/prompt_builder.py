from __future__ import annotations

import html
from pathlib import Path
from typing import Any, Sequence

from .paths import ANSWER_PROMPT_PATH, CLASSIFICATION_PROMPT_PATH


DETAIL_INSTRUCTIONS = {
    "concise_concept": "简洁解释核心概念，避免无关展开。",
    "procedure": "按清晰步骤回答，并指出证据中明确给出的注意事项。",
    "code_example": "提供必要的短Python示例并解释关键行，不扩展证据外API。",
    "comprehensive": "完整覆盖问题的各个核心方面、限制和必要权衡。",
}


def load_prompt(path: Path) -> str:
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        raise ValueError(f"Prompt文件为空：{path.name}")
    return content


def escape_untrusted(value: Any) -> str:
    return html.escape(str(value), quote=True)


def build_classification_messages(question: str) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": load_prompt(CLASSIFICATION_PROMPT_PATH),
        },
        {
            "role": "user",
            "content": (
                "<untrusted_question>\n"
                f"{escape_untrusted(question)}\n"
                "</untrusted_question>\n"
                "请按照系统要求只输出JSON对象。"
            ),
        },
    ]


def evidence_sort_key(hit: dict[str, Any]) -> tuple[Any, ...]:
    section = hit.get("section_path", [])
    if isinstance(section, list):
        section_text = " > ".join(str(item) for item in section)
    else:
        section_text = str(section)
    return (
        str(hit["source_path"]),
        section_text,
        int(hit["chunk_index"]),
        str(hit["chunk_id"]),
    )


def build_answer_messages(
    question: str,
    question_type: str,
    hits: Sequence[dict[str, Any]],
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    if question_type not in DETAIL_INSTRUCTIONS:
        raise ValueError(f"未知问题类型：{question_type}")
    ordered = sorted(hits, key=evidence_sort_key)
    evidence_payload: list[dict[str, Any]] = []
    evidence_parts: list[str] = []
    for hit in ordered:
        section = hit.get("section_path", [])
        section_text = (
            " > ".join(str(item) for item in section)
            if isinstance(section, list)
            else str(section)
        )
        safe_id = escape_untrusted(hit["chunk_id"])
        evidence_parts.extend(
            [
                f'<evidence chunk_id="{safe_id}">',
                f"<page_title>{escape_untrusted(hit['page_title'])}</page_title>",
                f"<section_path>{escape_untrusted(section_text)}</section_path>",
                f"<content>{escape_untrusted(hit['content'])}</content>",
                "</evidence>",
            ]
        )
        evidence_payload.append(
            {
                "chunk_id": str(hit["chunk_id"]),
                "page_title": str(hit["page_title"]),
                "section_path": list(section) if isinstance(section, list) else section,
                "source_path": str(hit["source_path"]),
                "chunk_index": int(hit["chunk_index"]),
                "content": str(hit["content"]),
            }
        )
    user_content = "\n".join(
        [
            "<untrusted_question>",
            escape_untrusted(question),
            "</untrusted_question>",
            "<answer_detail>",
            escape_untrusted(DETAIL_INSTRUCTIONS[question_type]),
            "</answer_detail>",
            "<untrusted_evidence_set>",
            *evidence_parts,
            "</untrusted_evidence_set>",
            "请严格按照系统中的回答Schema，只输出一个合法JSON对象。",
        ]
    )
    return (
        [
            {"role": "system", "content": load_prompt(ANSWER_PROMPT_PATH)},
            {"role": "user", "content": user_content},
        ],
        evidence_payload,
    )
