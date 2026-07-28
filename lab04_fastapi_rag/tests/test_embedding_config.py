from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.embedding_config import load_embedding_config


def test_frozen_embedding_config() -> None:
    config = load_embedding_config()

    assert config.model_id == "Qwen/Qwen3-Embedding-0.6B"
    assert config.revision == "97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3"
    assert config.dimension == 1024
    assert config.max_length == 8192
    assert config.document_instruction is None
    assert config.batch_size_for("cpu") == 2
    assert config.format_query("测试") == (
        "Instruct: Given a Chinese question about FastAPI, retrieve relevant "
        "passages from the FastAPI Chinese documentation that answer the "
        "question.\nQuery:测试"
    )


def test_invalid_revision_is_rejected(tmp_path: Path) -> None:
    payload = json.loads(
        Path("configs/embedding_config.json").read_text(encoding="utf-8")
    )
    payload["revision"] = "main"
    path = tmp_path / "embedding_config.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="40位"):
        load_embedding_config(path)
