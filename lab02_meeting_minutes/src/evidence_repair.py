from __future__ import annotations

import re
from collections import Counter
from typing import Any


EVIDENCE_REPAIR_VERSION = "evidence_repair_v2_qmsum_line_fallback"
QUOTE_VARIANTS = {
    "“": "",
    "”": "",
    "‘": "",
    "’": "",
    "'": "",
    '"': "",
}


def repair_payload_evidence(payload: dict[str, Any], source_text: str) -> None:
    for collection in ["attendees", "topics", "decisions", "action_items", "open_questions"]:
        for item in payload.get(collection, []):
            evidence = item.get("evidence")
            if not isinstance(evidence, str):
                continue
            repaired = repair_evidence(evidence, source_text)
            if repaired is not None:
                item["evidence"] = repaired


def repair_evidence(evidence: str, source_text: str) -> str | None:
    if evidence in source_text:
        return evidence
    normalized_source, source_indexes = _normalized_with_indexes(source_text)
    normalized_evidence, _ = _normalized_with_indexes(evidence)
    if not normalized_evidence:
        return None
    start = normalized_source.find(normalized_evidence)
    if start < 0:
        return _best_source_line(evidence, source_text)
    end = start + len(normalized_evidence) - 1
    return source_text[source_indexes[start] : source_indexes[end] + 1]


def _normalized_with_indexes(text: str) -> tuple[str, list[int]]:
    chars: list[str] = []
    indexes: list[int] = []
    for index, char in enumerate(text):
        if char.isspace():
            continue
        mapped = QUOTE_VARIANTS.get(char, char)
        if not mapped:
            continue
        chars.append(mapped)
        indexes.append(index)
    return "".join(chars), indexes


def _best_source_line(evidence: str, source_text: str) -> str | None:
    evidence_tokens = _content_tokens(evidence)
    if len(evidence_tokens) < 4:
        return None
    evidence_counts = Counter(evidence_tokens)
    best_line: str | None = None
    best_score = 0.0
    for line in source_text.splitlines():
        if not line.lstrip().startswith("- "):
            continue
        line_tokens = _content_tokens(line)
        if not line_tokens:
            continue
        overlap = sum(min(count, line_tokens.count(token)) for token, count in evidence_counts.items())
        score = overlap / max(len(evidence_tokens), 1)
        if score > best_score:
            best_score = score
            best_line = line
    if best_line is not None and best_score >= 0.45:
        return best_line
    return None


def _content_tokens(text: str) -> list[str]:
    normalized = text.lower()
    normalized = re.sub(r"\{[^}]+\}", " ", normalized)
    normalized = re.sub(r"^[\s*\-]*[a-z ]{1,40}:\s*", " ", normalized)
    return re.findall(r"[a-z0-9_]+", normalized)
