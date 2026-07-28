from __future__ import annotations

import re


_FULLWIDTH_TRANSLATION = str.maketrans(
    {
        **{chr(code): chr(code - 0xFEE0) for code in range(0xFF01, 0xFF5F)},
        "\u3000": " ",
        "，": ",",
        "。": ".",
        "；": ";",
        "：": ":",
        "！": "!",
        "？": "?",
        "（": "(",
        "）": ")",
        "【": "[",
        "】": "]",
    }
)
_REPEATED_WHITESPACE = re.compile(r"\s+")
_TRAILING_KEY_COLON = re.compile(r"\s*:+\s*$")


def normalize_text(text: str, *, is_key: bool = False) -> str:
    """Apply only the conservative normalization allowed by the task contract."""

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.translate(_FULLWIDTH_TRANSLATION)
    normalized = _REPEATED_WHITESPACE.sub(" ", normalized).strip()
    if is_key:
        normalized = _TRAILING_KEY_COLON.sub("", normalized).strip()
    return normalized
