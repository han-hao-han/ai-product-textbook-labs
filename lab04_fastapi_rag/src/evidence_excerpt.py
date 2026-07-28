from __future__ import annotations

import re
from typing import Any


IDENTIFIER_PATTERN = re.compile(
    r"[A-Za-z_][A-Za-z0-9_.:/-]*|[\u4e00-\u9fff]{2,}"
)
FENCE_PATTERN = re.compile(r"```.*?```", re.DOTALL)
TABLE_BLOCK_PATTERN = re.compile(
    r"(?:^|\n)((?:[^\n]*\|[^\n]*\n){2,})",
    re.MULTILINE,
)


def _terms(text: str) -> set[str]:
    terms: set[str] = set()
    for token in IDENTIFIER_PATTERN.findall(text):
        lowered = token.lower()
        if re.fullmatch(r"[\u4e00-\u9fff]+", token):
            for size in (2, 3, 4):
                terms.update(
                    token[index : index + size]
                    for index in range(max(0, len(token) - size + 1))
                )
        elif len(lowered) >= 2:
            terms.add(lowered)
    return terms


def _atomic_ranges(content: str) -> list[tuple[int, int]]:
    ranges = [(match.start(), match.end()) for match in FENCE_PATTERN.finditer(content)]
    ranges.extend(
        (match.start(1), match.end(1))
        for match in TABLE_BLOCK_PATTERN.finditer(content)
    )
    return sorted(ranges)


def _adjust_for_atomic_ranges(
    start: int,
    end: int,
    ranges: list[tuple[int, int]],
) -> tuple[int, int]:
    changed = True
    while changed:
        changed = False
        for atomic_start, atomic_end in ranges:
            intersects = start < atomic_end and end > atomic_start
            contains = start <= atomic_start and end >= atomic_end
            if intersects and not contains:
                start = min(start, atomic_start)
                end = max(end, atomic_end)
                changed = True
    return start, end


def select_evidence_excerpt(
    content: str,
    question: str,
    answer: str,
    *,
    target_chars: int = 250,
    minimum_chars: int = 200,
    maximum_chars: int = 300,
) -> dict[str, Any]:
    normalized = content.strip()
    if not normalized:
        raise ValueError("引用Chunk内容为空")
    query_terms = _terms(f"{question}\n{answer}")
    lowered = normalized.lower()
    positions: list[int] = []
    for term in query_terms:
        index = lowered.find(term.lower())
        if index >= 0:
            positions.append(index)
    center = min(positions) if positions else len(normalized) // 2
    start = max(0, center - target_chars // 3)
    end = min(len(normalized), start + target_chars)
    start = max(0, end - target_chars)
    start, end = _adjust_for_atomic_ranges(
        start,
        end,
        _atomic_ranges(normalized),
    )
    if end - start < minimum_chars and len(normalized) >= minimum_chars:
        missing = minimum_chars - (end - start)
        start = max(0, start - missing // 2)
        end = min(len(normalized), start + minimum_chars)
        start = max(0, end - minimum_chars)
        start, end = _adjust_for_atomic_ranges(
            start,
            end,
            _atomic_ranges(normalized),
        )
    if end - start > maximum_chars:
        ranges = _atomic_ranges(normalized)
        covering = [
            (atomic_start, atomic_end)
            for atomic_start, atomic_end in ranges
            if start <= atomic_start and end >= atomic_end
        ]
        if not covering:
            end = start + maximum_chars
    excerpt = normalized[start:end].strip()
    actual_start = normalized.find(excerpt, start, end + 1)
    actual_start = start if actual_start < 0 else actual_start
    return {
        "excerpt": excerpt,
        "start_offset": actual_start,
        "end_offset": actual_start + len(excerpt),
        "visible_characters": len(excerpt),
        "selection_method": (
            "query_answer_terms_continuous_window_atomic_code_table_v1"
        ),
    }
