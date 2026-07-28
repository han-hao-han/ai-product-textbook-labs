from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .io_utils import read_json
from .paths import EMBEDDING_CONFIG_PATH


REVISION_PATTERN = re.compile(r"^[0-9a-f]{40}$")
HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
GIT_BLOB_PATTERN = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class RequiredModelFile:
    path: str
    size_bytes: int
    sha256: str | None
    git_blob_sha1: str | None


@dataclass(frozen=True)
class EmbeddingConfig:
    schema_version: str
    model_id: str
    revision: str
    revision_last_modified: str
    official_url: str
    license: str
    dimension: int
    max_length: int
    padding_side: str
    pooling: str
    normalize: str
    storage_dtype: str
    inference_dtype: str
    document_instruction: None
    query_instruction: str
    query_template: str
    top_k: int
    demo_query: str
    batch_size: dict[str, int]
    runtime_dependencies: dict[str, str]
    required_files: tuple[RequiredModelFile, ...]

    def batch_size_for(self, device: str) -> int:
        key = "cuda" if device.startswith("cuda:") else device
        if key not in self.batch_size:
            raise ValueError(f"Embedding配置没有设备批大小：{device}")
        return self.batch_size[key]

    def format_query(self, query: str) -> str:
        return self.query_template.format(
            instruction=self.query_instruction,
            query=query,
        )


def _require_dict(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name}必须是JSON对象")
    return value


def load_embedding_config(
    path: Path = EMBEDDING_CONFIG_PATH,
) -> EmbeddingConfig:
    payload = _require_dict(read_json(path), "embedding_config")
    required = {
        "schema_version",
        "model_id",
        "revision",
        "revision_last_modified",
        "official_url",
        "license",
        "dimension",
        "max_length",
        "padding_side",
        "pooling",
        "normalize",
        "storage_dtype",
        "inference_dtype",
        "document_instruction",
        "query_instruction",
        "query_template",
        "top_k",
        "demo_query",
        "batch_size",
        "runtime_dependencies",
        "required_files",
    }
    missing = sorted(required - payload.keys())
    if missing:
        raise ValueError(f"embedding_config缺少字段：{', '.join(missing)}")
    if payload["schema_version"] != "qwen3_embedding_v1":
        raise ValueError("不支持的Embedding配置版本")
    revision = str(payload["revision"])
    if not REVISION_PATTERN.fullmatch(revision):
        raise ValueError("Embedding revision必须是40位小写十六进制SHA")
    if payload["document_instruction"] is not None:
        raise ValueError("文档Embedding不得配置任务指令")
    if "{instruction}" not in str(payload["query_template"]):
        raise ValueError("query_template必须包含{instruction}")
    if "{query}" not in str(payload["query_template"]):
        raise ValueError("query_template必须包含{query}")
    if int(payload["dimension"]) != 1024:
        raise ValueError("Embedding维度必须冻结为1024")
    if (
        payload["padding_side"] != "left"
        or payload["pooling"] != "last_non_padding_token"
        or payload["normalize"] != "L2"
        or payload["storage_dtype"] != "float32"
        or payload["inference_dtype"] != "float32"
    ):
        raise ValueError("Embedding数值或池化配置不符合冻结方案")

    batch_size_payload = _require_dict(payload["batch_size"], "batch_size")
    batch_size = {str(key): int(value) for key, value in batch_size_payload.items()}
    if set(batch_size) != {"cpu", "cuda"} or any(
        value <= 0 for value in batch_size.values()
    ):
        raise ValueError("batch_size必须为cpu和cuda配置正整数")

    dependencies_payload = _require_dict(
        payload["runtime_dependencies"],
        "runtime_dependencies",
    )
    dependencies = {
        str(key): str(value) for key, value in dependencies_payload.items()
    }
    expected_dependencies = {
        "torch",
        "numpy",
        "transformers",
        "huggingface-hub",
        "tokenizers",
        "safetensors",
    }
    if set(dependencies) != expected_dependencies:
        raise ValueError("Embedding运行依赖集合与冻结方案不一致")

    files_payload = payload["required_files"]
    if not isinstance(files_payload, list) or not files_payload:
        raise ValueError("required_files必须是非空数组")
    files: list[RequiredModelFile] = []
    seen_paths: set[str] = set()
    for raw_item in files_payload:
        item = _require_dict(raw_item, "required_files条目")
        file_path = str(item.get("path", ""))
        size_bytes = int(item.get("size_bytes", 0))
        sha256 = item.get("sha256")
        git_blob_sha1 = item.get("git_blob_sha1")
        if not file_path or size_bytes <= 0:
            raise ValueError("模型文件必须包含path和正整数size_bytes")
        if file_path in seen_paths:
            raise ValueError(f"重复模型文件：{file_path}")
        seen_paths.add(file_path)
        if bool(sha256) == bool(git_blob_sha1):
            raise ValueError(
                f"模型文件必须且只能配置sha256或git_blob_sha1：{file_path}"
            )
        if sha256 is not None and not HASH_PATTERN.fullmatch(str(sha256)):
            raise ValueError(f"模型文件SHA-256无效：{file_path}")
        if git_blob_sha1 is not None and not GIT_BLOB_PATTERN.fullmatch(
            str(git_blob_sha1)
        ):
            raise ValueError(f"模型文件Git blob SHA-1无效：{file_path}")
        files.append(
            RequiredModelFile(
                path=file_path,
                size_bytes=size_bytes,
                sha256=str(sha256) if sha256 else None,
                git_blob_sha1=(
                    str(git_blob_sha1) if git_blob_sha1 else None
                ),
            )
        )

    return EmbeddingConfig(
        schema_version=str(payload["schema_version"]),
        model_id=str(payload["model_id"]),
        revision=revision,
        revision_last_modified=str(payload["revision_last_modified"]),
        official_url=str(payload["official_url"]),
        license=str(payload["license"]),
        dimension=int(payload["dimension"]),
        max_length=int(payload["max_length"]),
        padding_side=str(payload["padding_side"]),
        pooling=str(payload["pooling"]),
        normalize=str(payload["normalize"]),
        storage_dtype=str(payload["storage_dtype"]),
        inference_dtype=str(payload["inference_dtype"]),
        document_instruction=None,
        query_instruction=str(payload["query_instruction"]),
        query_template=str(payload["query_template"]),
        top_k=int(payload["top_k"]),
        demo_query=str(payload["demo_query"]),
        batch_size=batch_size,
        runtime_dependencies=dependencies,
        required_files=tuple(files),
    )
