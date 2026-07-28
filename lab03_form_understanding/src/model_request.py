from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any

from .prompt_loader import load_extraction_prompt


SUPPORTED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


def image_to_data_url(image_path: Path) -> str:
    if not image_path.is_file():
        raise FileNotFoundError(f"图片不存在：{image_path}")
    mime_type, _ = mimetypes.guess_type(image_path.name)
    if mime_type not in SUPPORTED_IMAGE_TYPES:
        raise ValueError(f"不支持的图片格式：{image_path.suffix or '无扩展名'}")
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def build_chat_completion_request(
    image_path: Path,
    *,
    model: str,
    temperature: float = 0,
    prompt: str | None = None,
) -> dict[str, Any]:
    if not model.strip():
        raise ValueError("模型名称不能为空")
    system_prompt = prompt if prompt is not None else load_extraction_prompt()
    if not system_prompt.strip():
        raise ValueError("Prompt不能为空")

    return {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": image_to_data_url(image_path)},
                    },
                    {
                        "type": "text",
                        "text": "请识别这张中文表单，并严格以JSON格式返回。",
                    },
                ],
            },
        ],
        "response_format": {"type": "json_object"},
        "temperature": temperature,
        "extra_body": {"enable_thinking": False},
    }
