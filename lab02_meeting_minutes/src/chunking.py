from __future__ import annotations

import re


CHUNKING_VERSION = "chunking_v1_h3_draft"
SPEAKER_LINE_RE = re.compile(r"^\s*(?:\[([\u4e00-\u9fa5A-Za-z0-9_]{1,20})\]|([\u4e00-\u9fa5A-Za-z0-9_]{1,20})\s*[:：\-])")


def split_into_turns(text: str) -> list[str]:
    turns: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if SPEAKER_LINE_RE.match(line) and current:
            turns.append("\n".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        last = "\n".join(current).strip()
        if last:
            turns.append(last)
    return [turn for turn in turns if turn]


def chunk_by_turns(text: str, max_chars: int, overlap_turns: int = 0) -> list[str]:
    if max_chars <= 0:
        raise ValueError("max_chars must be greater than 0")
    if overlap_turns < 0:
        raise ValueError("overlap_turns must not be negative")
    turns = split_into_turns(text)
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for turn in turns:
        extra_len = len(turn) + (1 if current else 0)
        if current and current_len + extra_len > max_chars:
            chunks.append("\n".join(current))
            current = current[-overlap_turns:] if overlap_turns else []
            current_len = sum(len(item) for item in current) + max(len(current) - 1, 0)
        current.append(turn)
        current_len += len(turn) + (1 if current_len else 0)
    if current:
        chunks.append("\n".join(current))
    return chunks or [text]
