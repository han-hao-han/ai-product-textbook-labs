from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = REPOSITORY_ROOT / ".env"


@dataclass(frozen=True)
class LLMSettings:
    """统一的大模型 API 配置。"""

    api_key: str
    base_url: str
    model: str
    temperature: float


def load_llm_settings() -> LLMSettings:
    """从项目根目录的 .env 加载大模型配置。"""
    load_dotenv(
        dotenv_path=ENV_PATH,
        override=False,
    )

    api_key = os.getenv(
        "LLM_API_KEY",
        "",
    ).strip()

    base_url = os.getenv(
        "LLM_BASE_URL",
        "",
    ).strip()

    model = os.getenv(
        "LLM_MODEL",
        "",
    ).strip()

    temperature_text = os.getenv(
        "LLM_TEMPERATURE",
        "0",
    ).strip()

    missing_fields: list[str] = []

    if not api_key:
        missing_fields.append("LLM_API_KEY")

    if not base_url:
        missing_fields.append("LLM_BASE_URL")

    if not model:
        missing_fields.append("LLM_MODEL")

    if missing_fields:
        raise ValueError(
            "缺少环境变量："
            + ", ".join(missing_fields)
            + f"。请检查 {ENV_PATH}"
        )

    try:
        temperature = float(
            temperature_text
        )
    except ValueError as error:
        raise ValueError(
            "LLM_TEMPERATURE 必须是数字，"
            f"当前值为 {temperature_text!r}"
        ) from error

    if not 0 <= temperature <= 2:
        raise ValueError(
            "LLM_TEMPERATURE 必须位于 0 到 2 之间"
        )

    return LLMSettings(
        api_key=api_key,
        base_url=base_url.rstrip("/"),
        model=model,
        temperature=temperature,
    )