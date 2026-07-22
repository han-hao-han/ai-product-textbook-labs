from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


DEFAULT_MODEL = "deepseek-v4-flash"
DEFAULT_BASE_URL = "https://api.deepseek.com"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    api_key: str
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    temperature: float = 0.0
    timeout_seconds: int = 60
    max_input_chars: int = 12000
    chunk_max_chars: int = 3500
    chunk_overlap_turns: int = 1


def load_settings() -> Settings:
    load_dotenv(PROJECT_ROOT / ".env")
    load_dotenv(PROJECT_ROOT / "lab02_meeting_minutes" / ".env", override=True)
    return Settings(
        api_key=os.getenv("LLM_API_KEY", ""),
        base_url=os.getenv("LLM_BASE_URL", DEFAULT_BASE_URL),
        model=os.getenv("LLM_MODEL", DEFAULT_MODEL),
        temperature=float(os.getenv("LLM_TEMPERATURE", "0")),
        timeout_seconds=int(os.getenv("LLM_TIMEOUT_SECONDS", "60")),
        max_input_chars=int(os.getenv("MAX_INPUT_CHARS", "12000")),
        chunk_max_chars=int(os.getenv("CHUNK_MAX_CHARS", "3500")),
        chunk_overlap_turns=int(os.getenv("CHUNK_OVERLAP_TURNS", "1")),
    )


def validate_real_api_settings(settings: Settings) -> None:
    if not settings.api_key:
        raise ValueError("LLM_API_KEY is not configured")
    if not settings.base_url:
        raise ValueError("LLM_BASE_URL is not configured")
    if not settings.model:
        raise ValueError("LLM_MODEL is not configured")
