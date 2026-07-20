from __future__ import annotations

from openai import OpenAI

from common.config import LLMSettings


def create_openai_client(
    settings: LLMSettings,
) -> OpenAI:
    """创建 OpenAI-compatible API 客户端。"""
    return OpenAI(
        api_key=settings.api_key,
        base_url=settings.base_url,
        timeout=120.0,
        max_retries=0,
    )