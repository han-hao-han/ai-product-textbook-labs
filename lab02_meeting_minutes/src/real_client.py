from __future__ import annotations

from typing import Any

from openai import OpenAI

from .budget import ensure_budget_available, record_api_call
from .config import Settings, validate_real_api_settings
from .json_utils import parse_json_object
from .prompts import SYSTEM_PROMPT, USER_TEMPLATE


class RealLLMClient:
    def __init__(self, settings: Settings) -> None:
        validate_real_api_settings(settings)
        self.settings = settings
        self.client = OpenAI(api_key=settings.api_key, base_url=settings.base_url, timeout=settings.timeout_seconds)

    def extract(self, meeting_id: str, meeting_text: str, meeting_date: str | None) -> tuple[dict[str, Any], dict[str, Any]]:
        ensure_budget_available()
        metadata: dict[str, Any] = {"model": self.settings.model, "status": "started", "usage": {}}
        try:
            response = self.client.chat.completions.create(
                model=self.settings.model,
                temperature=self.settings.temperature,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": USER_TEMPLATE.format(meeting_id=meeting_id, meeting_date=meeting_date or "未提供", meeting_text=meeting_text)},
                ],
            )
            content = response.choices[0].message.content or ""
            metadata["status"] = "success"
            if response.usage is not None:
                metadata["usage"] = response.usage.model_dump()
            return parse_json_object(content), metadata
        except Exception as exc:
            metadata["status"] = "failed"
            metadata["error_type"] = type(exc).__name__
            metadata["error_message"] = str(exc)
            raise
        finally:
            budget = record_api_call()
            metadata["api_budget_used"] = budget["used"]
            metadata["api_budget_remaining"] = budget["remaining"]
