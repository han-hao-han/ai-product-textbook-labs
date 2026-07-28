from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

from .io_utils import sha256_text
from .source_config import ChunkingConfig


HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
CJK_PATTERN = re.compile(
    r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
    r"\u3040-\u30ff\uac00-\ud7af]"
)
ASCII_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|[^\s]")
TABLE_SEPARATOR_PATTERN = re.compile(
    r"^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?\s*$"
)
FENCE_PATTERN = re.compile(r"^\s*(?P<fence>`{3,}|~{3,})")


@dataclass(frozen=True)
class Block:
    text: str
    section_path: tuple[str, ...]
    kind: str
    token_count: int


@dataclass
class ChunkDraft:
    blocks: list[Block]
    overlap_tokens: int
    boundary_reason: str


def estimate_tokens(text: str) -> int:
    cjk_count = len(CJK_PATTERN.findall(text))
    without_cjk = CJK_PATTERN.sub(" ", text)
    ascii_units = ASCII_TOKEN_PATTERN.findall(without_cjk)
    ascii_count = sum(
        max(1, math.ceil(len(unit) / 4))
        if re.fullmatch(r"[A-Za-z0-9_]+", unit)
        else 1
        for unit in ascii_units
    )
    return cjk_count + ascii_count


def _flush_paragraph(
    paragraph: list[str],
    section_path: tuple[str, ...],
    blocks: list[Block],
) -> None:
    if not paragraph:
        return
    text = "\n".join(paragraph).strip()
    paragraph.clear()
    if text:
        blocks.append(
            Block(
                text=text,
                section_path=section_path,
                kind="text",
                token_count=estimate_tokens(text),
            )
        )


def parse_blocks(markdown: str, page_title: str) -> list[Block]:
    lines = markdown.splitlines()
    headings = [page_title]
    current_section = (page_title,)
    blocks: list[Block] = []
    paragraph: list[str] = []
    index = 0

    while index < len(lines):
        line = lines[index]
        heading = HEADING_PATTERN.match(line)
        if heading:
            _flush_paragraph(paragraph, current_section, blocks)
            level = len(heading.group(1))
            title = heading.group(2).strip()
            if level == 1:
                headings = [title]
            else:
                headings = headings[: level - 1]
                while len(headings) < level - 1:
                    headings.append("(未命名层级)")
                headings.append(title)
            current_section = tuple(headings)
            index += 1
            continue

        fence_match = FENCE_PATTERN.match(line)
        if fence_match:
            _flush_paragraph(paragraph, current_section, blocks)
            fence = fence_match.group("fence")
            code_lines = [line]
            index += 1
            while index < len(lines):
                code_lines.append(lines[index])
                closing = FENCE_PATTERN.match(lines[index])
                if closing and closing.group("fence").startswith(fence):
                    index += 1
                    break
                index += 1
            text = "\n".join(code_lines).strip()
            blocks.append(
                Block(
                    text=text,
                    section_path=current_section,
                    kind="code",
                    token_count=estimate_tokens(text),
                )
            )
            continue

        if (
            "|" in line
            and index + 1 < len(lines)
            and TABLE_SEPARATOR_PATTERN.match(lines[index + 1])
        ):
            _flush_paragraph(paragraph, current_section, blocks)
            table_lines = [line, lines[index + 1]]
            index += 2
            while index < len(lines) and "|" in lines[index] and lines[index].strip():
                table_lines.append(lines[index])
                index += 1
            text = "\n".join(table_lines).strip()
            blocks.append(
                Block(
                    text=text,
                    section_path=current_section,
                    kind="table",
                    token_count=estimate_tokens(text),
                )
            )
            continue

        if not line.strip():
            _flush_paragraph(paragraph, current_section, blocks)
        else:
            paragraph.append(line)
        index += 1

    _flush_paragraph(paragraph, current_section, blocks)
    return blocks


def _split_text_block(block: Block, max_tokens: int) -> list[Block]:
    if block.token_count <= max_tokens or block.kind in {"code", "table"}:
        return [block]
    units = [
        unit.strip()
        for unit in re.split(r"(?<=[。！？.!?])\s*|\n+", block.text)
        if unit.strip()
    ]
    if len(units) <= 1:
        units = [
            block.text[index : index + max_tokens]
            for index in range(0, len(block.text), max_tokens)
        ]

    results: list[Block] = []
    current: list[str] = []
    current_tokens = 0
    for unit in units:
        unit_tokens = estimate_tokens(unit)
        if current and current_tokens + unit_tokens > max_tokens:
            text = "\n".join(current)
            results.append(
                Block(
                    text=text,
                    section_path=block.section_path,
                    kind="text",
                    token_count=estimate_tokens(text),
                )
            )
            current = []
            current_tokens = 0
        current.append(unit)
        current_tokens += unit_tokens
    if current:
        text = "\n".join(current)
        results.append(
            Block(
                text=text,
                section_path=block.section_path,
                kind="text",
                token_count=estimate_tokens(text),
            )
        )
    return results


def _display_heading(title: str) -> str:
    return re.sub(r"\s+\{.*\}\s*$", "", title).strip()


def _common_prefix_length(
    left: tuple[str, ...],
    right: tuple[str, ...],
) -> int:
    length = 0
    for left_item, right_item in zip(left, right):
        if left_item != right_item:
            break
        length += 1
    return length


def _render_blocks(blocks: list[Block]) -> str:
    output: list[str] = []
    previous_path: tuple[str, ...] = ()
    for block in blocks:
        if block.section_path != previous_path:
            common = _common_prefix_length(previous_path, block.section_path)
            for index, heading in enumerate(
                block.section_path[common:],
                start=common + 1,
            ):
                output.append(
                    f"{'#' * min(index, 6)} {_display_heading(heading)}"
                )
            previous_path = block.section_path
        output.append(block.text)
    return "\n\n".join(output).strip()


def _render_token_count(blocks: list[Block]) -> int:
    return estimate_tokens(_render_blocks(blocks))


def _overlap_tail(
    blocks: list[Block],
    config: ChunkingConfig,
) -> tuple[list[Block], int]:
    selected: list[Block] = []
    if not blocks:
        return [], 0
    overlap_section = blocks[-1].section_path
    for block in reversed(blocks):
        if block.section_path != overlap_section:
            break
        if block.kind in {"code", "table"} and block.token_count > config.overlap_max_tokens:
            continue
        candidate = [block, *selected]
        candidate_tokens = _render_token_count(candidate)
        if selected and candidate_tokens > config.overlap_max_tokens:
            break
        if not selected and candidate_tokens > config.overlap_max_tokens:
            continue
        selected = candidate
        if candidate_tokens >= config.overlap_target_tokens:
            break
    tokens = _render_token_count(selected) if selected else 0
    if tokens < config.overlap_min_tokens:
        return [], 0
    return selected, tokens


def _append_draft(
    drafts: list[ChunkDraft],
    blocks: list[Block],
    overlap_tokens: int,
    boundary_reason: str,
) -> None:
    if blocks:
        drafts.append(
            ChunkDraft(
                blocks=list(blocks),
                overlap_tokens=overlap_tokens,
                boundary_reason=boundary_reason,
            )
        )


def _rebalance_document_tail(
    drafts: list[ChunkDraft],
    config: ChunkingConfig,
) -> None:
    if len(drafts) < 2:
        return
    previous = drafts[-2]
    tail = drafts[-1]
    if (
        tail.boundary_reason != "document_tail"
        or tail.overlap_tokens
        or previous.overlap_tokens
        or _render_token_count(tail.blocks) >= config.target_min_tokens
        or _render_token_count(previous.blocks) > config.target_max_tokens
    ):
        return

    combined = [*previous.blocks, *tail.blocks]
    if _render_token_count(combined) <= config.target_max_tokens:
        previous.blocks = combined
        previous.boundary_reason = "merged_document_tail"
        drafts.pop()
        return

    while len(previous.blocks) > 1:
        moved = previous.blocks[-1]
        candidate_previous = previous.blocks[:-1]
        candidate_tail = [moved, *tail.blocks]
        if (
            _render_token_count(candidate_previous) < config.target_min_tokens
            or _render_token_count(candidate_tail) > config.target_max_tokens
        ):
            break
        previous.blocks = candidate_previous
        tail.blocks = candidate_tail
        previous.boundary_reason = "rebalanced_for_document_tail"
        tail.boundary_reason = "rebalanced_document_tail"
        if _render_token_count(tail.blocks) >= config.target_min_tokens:
            break


def chunk_document(
    markdown: str,
    document: dict[str, Any],
    config: ChunkingConfig,
) -> list[dict[str, Any]]:
    parsed = parse_blocks(markdown, document["page_title"])
    expanded = [
        split_block
        for block in parsed
        for split_block in _split_text_block(
            block,
            max(
                1,
                config.target_max_tokens
                - estimate_tokens(
                    "\n\n".join(
                        f"{'#' * min(index, 6)} {_display_heading(heading)}"
                        for index, heading in enumerate(
                            block.section_path,
                            start=1,
                        )
                    )
                ),
            ),
        )
    ]
    drafts: list[ChunkDraft] = []
    current: list[Block] = []
    current_overlap = 0

    for block in expanded:
        single_tokens = _render_token_count([block])
        oversized_atomic = (
            block.kind in {"code", "table"}
            and single_tokens > config.target_max_tokens
        )
        if oversized_atomic:
            if current and _render_token_count(current) < config.target_min_tokens:
                current.append(block)
                _append_draft(
                    drafts,
                    current,
                    current_overlap,
                    f"oversized_atomic_{block.kind}_with_context",
                )
            else:
                _append_draft(
                    drafts,
                    current,
                    current_overlap,
                    "before_oversized_atomic_block",
                )
                _append_draft(
                    drafts,
                    [block],
                    0,
                    f"oversized_atomic_{block.kind}",
                )
            current = []
            current_overlap = 0
            continue

        if current and _render_token_count([*current, block]) > config.target_max_tokens:
            previous = list(current)
            _append_draft(
                drafts,
                previous,
                current_overlap,
                "target_max_reached",
            )
            overlap: list[Block] = []
            overlap_tokens = 0
            if previous[-1].section_path == block.section_path:
                overlap, overlap_tokens = _overlap_tail(previous, config)
                while (
                    overlap
                    and _render_token_count([*overlap, block])
                    > config.target_max_tokens
                ):
                    overlap = overlap[1:]
                    overlap_tokens = (
                        _render_token_count(overlap) if overlap else 0
                    )
                if overlap_tokens < config.overlap_min_tokens:
                    overlap = []
                    overlap_tokens = 0
            current = [*overlap, block]
            current_overlap = overlap_tokens
        else:
            current.append(block)

    _append_draft(
        drafts,
        current,
        current_overlap,
        "document_tail",
    )
    _rebalance_document_tail(drafts, config)

    chunks = [
        _make_chunk(
            draft.blocks,
            document,
            chunk_index,
            draft.overlap_tokens,
            draft.boundary_reason,
            config,
            len(drafts),
        )
        for chunk_index, draft in enumerate(drafts)
    ]
    return chunks


def _make_chunk(
    blocks: list[Block],
    document: dict[str, Any],
    chunk_index: int,
    overlap_tokens: int,
    boundary_reason: str,
    config: ChunkingConfig,
    document_chunk_count: int,
) -> dict[str, Any]:
    content = _render_blocks(blocks)
    content_hash = sha256_text(content)
    identity = (
        f"{document['source_path']}\n"
        f"{'/'.join(blocks[0].section_path)}\n"
        f"{chunk_index}\n{content_hash}"
    )
    chunk_id = f"fastapi_{sha256_text(identity)[:20]}"
    token_count = estimate_tokens(content)
    section_paths: list[list[str]] = []
    for block in blocks:
        path = list(block.section_path)
        if path not in section_paths:
            section_paths.append(path)
    under_min_reason = None
    if token_count < config.target_min_tokens:
        if document_chunk_count == 1:
            under_min_reason = "short_document"
        elif "tail" in boundary_reason:
            under_min_reason = "document_tail"
        elif boundary_reason == "before_oversized_atomic_block":
            under_min_reason = "before_oversized_atomic_block"
        elif boundary_reason == "target_max_reached":
            under_min_reason = "next_block_would_exceed_target_max"
        else:
            under_min_reason = "semantic_block_boundary"
    over_max_reason = None
    if token_count > config.target_max_tokens:
        if any(block.kind == "code" for block in blocks):
            over_max_reason = "oversized_atomic_code_block"
        elif any(block.kind == "table" for block in blocks):
            over_max_reason = "oversized_atomic_table"
        else:
            over_max_reason = "oversized_indivisible_text_block"
    return {
        "chunk_id": chunk_id,
        "page_title": document["page_title"],
        "section_path": section_paths[0],
        "section_paths": section_paths,
        "source_path": document["source_path"],
        "source_commit": document["commit"],
        "source_url": document["source_url"],
        "chunk_index": chunk_index,
        "token_count": token_count,
        "token_count_method": config.token_count_method,
        "overlap_tokens": overlap_tokens,
        "chunk_boundary_reason": boundary_reason,
        "under_min_reason": under_min_reason,
        "over_max_reason": over_max_reason,
        "contains_code": any(block.kind == "code" for block in blocks),
        "contains_table": any(block.kind == "table" for block in blocks),
        "content_sha256": content_hash,
        "content": content,
    }
