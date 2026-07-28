from __future__ import annotations

from pathlib import Path


def read_text_file(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"input file does not exist: {path}")
    if path.suffix.lower() not in {".md", ".txt"}:
        raise ValueError("only .md and .txt inputs are supported")
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError("input file is empty")
    return text


def infer_meeting_id(path: Path, text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return path.stem


def infer_meeting_date(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("会议日期："):
            value = stripped.removeprefix("会议日期：").strip()
            return None if value in {"未提供", "无", ""} else value
    return None


def write_json(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
