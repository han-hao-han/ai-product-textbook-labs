from __future__ import annotations

import importlib.metadata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .io_utils import read_json
from .paths import GENERATION_CONFIG_PATH


QUESTION_TYPES = {
    "concise_concept",
    "procedure",
    "code_example",
    "comprehensive",
}


@dataclass(frozen=True)
class GenerationConfig:
    schema_version: str
    status: str
    provider: str
    region: str
    base_url: str
    api_key_environment_variable: str
    client_api: str
    model: str
    response_format: dict[str, str]
    stream: bool
    temperature: float
    enable_thinking: bool
    output_token_cap: None
    dynamic_length_strategy: str
    timeout_seconds: float
    retry_wait_seconds: float
    temporary_error_max_retries: int
    question_types: tuple[str, ...]
    runtime_dependencies: dict[str, str]
    official_references: tuple[str, ...]


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field}必须是JSON对象")
    return value


def load_generation_config(
    path: Path = GENERATION_CONFIG_PATH,
) -> GenerationConfig:
    payload = _mapping(read_json(path), "generation_config")
    if payload.get("schema_version") != "generation_config_v1":
        raise ValueError("不支持的Generation配置版本")
    if payload.get("status") != "h3_generation_candidate_user_confirmed":
        raise ValueError("Generation方案尚未由用户确认")
    if (
        payload.get("provider") != "aliyun_model_studio"
        or payload.get("region") != "cn-beijing"
        or payload.get("base_url")
        != "https://dashscope.aliyuncs.com/compatible-mode/v1"
        or payload.get("client_api")
        != "openai_compatible_chat_completions"
        or payload.get("model") != "qwen3.7-plus-2026-05-26"
    ):
        raise ValueError("在线模型或OpenAI-compatible端点偏离H3确认方案")
    if payload.get("api_key_environment_variable") != "DASHSCOPE_API_KEY":
        raise ValueError("API Key环境变量名必须为DASHSCOPE_API_KEY")

    structured = _mapping(payload.get("structured_output"), "structured_output")
    if (
        structured.get("mode") != "json_object"
        or structured.get("response_format") != {"type": "json_object"}
        or structured.get("prompt_must_explicitly_request_json") is not True
        or structured.get("prompt_only_json_fallback") is not False
    ):
        raise ValueError("结构化输出配置偏离已确认JSON Mode方案")
    request = _mapping(payload.get("request"), "request")
    if (
        request.get("stream") is not False
        or float(request.get("temperature", -1)) != 0
        or request.get("enable_thinking") is not False
        or request.get("output_token_cap") is not None
        or request.get("dynamic_length_strategy")
        != "prompt_detail_only_no_output_token_cap"
        or float(request.get("timeout_seconds", 0)) != 60
        or float(request.get("retry_wait_seconds", 0)) != 2
        or int(request.get("temporary_error_max_retries", -1)) != 1
    ):
        raise ValueError("请求参数偏离H3确认方案A")

    question_types = tuple(str(item) for item in payload.get("question_types", []))
    if set(question_types) != QUESTION_TYPES or len(question_types) != 4:
        raise ValueError("问题类型集合不符合冻结方案")
    dependencies = {
        str(key): str(value)
        for key, value in _mapping(
            payload.get("runtime_dependencies"),
            "runtime_dependencies",
        ).items()
    }
    if set(dependencies) != {
        "openai",
        "pydantic",
        "python-dotenv",
        "streamlit",
    }:
        raise ValueError("Generation依赖集合不符合冻结方案")
    references = tuple(str(item) for item in payload.get("official_references", []))
    if not references or any(not item.startswith("https://help.aliyun.com/") for item in references):
        raise ValueError("Generation配置缺少阿里云官方参考链接")
    return GenerationConfig(
        schema_version=str(payload["schema_version"]),
        status=str(payload["status"]),
        provider=str(payload["provider"]),
        region=str(payload["region"]),
        base_url=str(payload["base_url"]),
        api_key_environment_variable=str(
            payload["api_key_environment_variable"]
        ),
        client_api=str(payload["client_api"]),
        model=str(payload["model"]),
        response_format=dict(structured["response_format"]),
        stream=False,
        temperature=0.0,
        enable_thinking=False,
        output_token_cap=None,
        dynamic_length_strategy=str(request["dynamic_length_strategy"]),
        timeout_seconds=float(request["timeout_seconds"]),
        retry_wait_seconds=float(request["retry_wait_seconds"]),
        temporary_error_max_retries=int(
            request["temporary_error_max_retries"]
        ),
        question_types=question_types,
        runtime_dependencies=dependencies,
        official_references=references,
    )


def installed_generation_dependency_versions(
    config: GenerationConfig,
) -> dict[str, str]:
    versions: dict[str, str] = {}
    problems: list[str] = []
    for distribution, expected in config.runtime_dependencies.items():
        try:
            actual = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            problems.append(f"{distribution}: missing")
            continue
        versions[distribution] = actual
        if actual != expected:
            problems.append(
                f"{distribution}: expected={expected}, actual={actual}"
            )
    if problems:
        raise RuntimeError("Generation依赖未满足冻结版本；" + "；".join(problems))
    return versions
