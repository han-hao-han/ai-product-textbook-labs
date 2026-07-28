from __future__ import annotations

import json

from pydantic import ValidationError

from .schemas import FormExtractionResult


class ModelResponseError(ValueError):
    """A model response failed a deterministic parsing or validation stage."""

    def __init__(self, stage: str, message: str) -> None:
        super().__init__(message)
        self.stage = stage


def parse_model_response(response_text: str) -> FormExtractionResult:
    if not isinstance(response_text, str) or not response_text.strip():
        raise ModelResponseError("empty_response", "模型返回内容为空")

    stripped = response_text.strip()
    if stripped.startswith("```") or stripped.endswith("```"):
        raise ModelResponseError("json_parse", "模型返回了Markdown代码围栏，不是直接JSON")

    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as error:
        raise ModelResponseError(
            "json_parse",
            f"模型返回内容不是合法JSON：第{error.lineno}行第{error.colno}列",
        ) from error

    if not isinstance(payload, dict):
        raise ModelResponseError("schema_validation", "模型JSON顶层必须是对象")

    try:
        return FormExtractionResult.model_validate(payload)
    except ValidationError as error:
        raise ModelResponseError("schema_validation", str(error)) from error
