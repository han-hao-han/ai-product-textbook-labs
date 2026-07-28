from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

from openai import OpenAI

from .model_request import build_chat_completion_request
from .settings import ModelSettings


class ModelCallError(RuntimeError):
    """The provider returned no usable assistant text."""


@dataclass(frozen=True)
class VisionCallResult:
    response_text: str
    requested_model: str
    returned_model: str
    finish_reason: str | None
    usage: dict[str, Any]
    elapsed_seconds: float


class OpenAICompatibleVisionClient:
    def __init__(self, settings: ModelSettings, client: Any | None = None) -> None:
        self.settings = settings
        self._client = client or OpenAI(
            api_key=settings.api_key,
            base_url=settings.base_url,
            timeout=settings.timeout_seconds,
        )

    def extract(self, image_path: Path, *, prompt: str | None = None) -> VisionCallResult:
        request = build_chat_completion_request(
            image_path,
            model=self.settings.model,
            temperature=self.settings.temperature,
            prompt=prompt,
        )
        started = perf_counter()
        response = self._client.chat.completions.create(**request)
        elapsed = round(perf_counter() - started, 4)
        if not response.choices:
            raise ModelCallError("模型响应不包含choices")
        choice = response.choices[0]
        content = choice.message.content
        if not isinstance(content, str) or not content.strip():
            raise ModelCallError("模型响应内容为空")
        usage = (
            response.usage.model_dump(mode="json")
            if response.usage is not None
            else {}
        )
        return VisionCallResult(
            response_text=content,
            requested_model=self.settings.model,
            returned_model=str(response.model or self.settings.model),
            finish_reason=choice.finish_reason,
            usage=usage,
            elapsed_seconds=elapsed,
        )
