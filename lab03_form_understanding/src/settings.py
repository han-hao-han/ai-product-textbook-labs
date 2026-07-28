from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from dotenv import dotenv_values

from .paths import PROJECT_ROOT


MODEL_CANDIDATE_PATH = PROJECT_ROOT / "configs" / "model_candidate.json"
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"


@dataclass(frozen=True)
class ModelSettings:
    api_key: str
    base_url: str
    model: str
    temperature: float
    timeout_seconds: float


def load_model_candidate(path: Path = MODEL_CANDIDATE_PATH) -> dict:
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, dict) or not payload.get("model_id"):
        raise ValueError("模型候选配置缺少model_id")
    return payload


def load_model_settings(env_path: Path = DEFAULT_ENV_PATH) -> ModelSettings:
    candidate = load_model_candidate()
    file_values = dotenv_values(env_path) if env_path.is_file() else {}

    def value(name: str, default: str = "") -> str:
        raw = os.getenv(name)
        if raw is None:
            raw = file_values.get(name, default)
        return str(raw or default).strip()

    settings = ModelSettings(
        api_key=value("LLM_API_KEY"),
        base_url=value("LLM_BASE_URL", candidate["base_url"]).rstrip("/"),
        model=value("LLM_MODEL", candidate["model_id"]),
        temperature=float(value("LLM_TEMPERATURE", "0")),
        timeout_seconds=float(
            value(
                "LLM_TIMEOUT_SECONDS",
                str(candidate["request_options"]["timeout_seconds"]),
            )
        ),
    )
    validate_model_settings(settings, candidate)
    return settings


def validate_model_settings(settings: ModelSettings, candidate: dict) -> None:
    if not settings.api_key:
        raise ValueError("LLM_API_KEY未配置；请复制.env.example为.env并填写实验账号密钥")
    if settings.model != candidate["model_id"]:
        raise ValueError(
            "H3核验必须使用候选模型"
            f"{candidate['model_id']}，当前配置为{settings.model}"
        )
    parsed = urlparse(settings.base_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("LLM_BASE_URL必须是有效的HTTPS地址")
    if settings.timeout_seconds <= 0:
        raise ValueError("LLM_TIMEOUT_SECONDS必须大于0")


def require_h3_frozen(candidate: dict) -> None:
    if candidate.get("status") != "h3_frozen_user_confirmed":
        raise ValueError("H3尚未由用户确认，不能进入正式视觉识别")
    confirmation = candidate.get("h3_confirmation")
    required_flags = (
        "model_and_calling_method",
        "prompt_v1",
        "schema_v1",
        "dataset_annotation_consistency_layer",
        "diagnostic_hints_do_not_auto_judge",
        "final_reference_accuracy_gate",
    )
    if not isinstance(confirmation, dict) or not all(
        confirmation.get(name) is True for name in required_flags
    ) or confirmation.get("comparison_policy_version") != "v2":
        raise ValueError("H3确认记录不完整，不能进入正式视觉识别")
