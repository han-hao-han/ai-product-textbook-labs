from __future__ import annotations

from pathlib import Path

from .paths import PROJECT_ROOT
from .schemas import PROMPT_VERSION


PROMPT_PATH = PROJECT_ROOT / "prompts" / f"form_extraction_{PROMPT_VERSION}.txt"


def load_extraction_prompt(prompt_path: Path = PROMPT_PATH) -> str:
    prompt = prompt_path.read_text(encoding="utf-8").strip()
    if not prompt:
        raise ValueError(f"Prompt文件为空：{prompt_path}")
    return prompt
