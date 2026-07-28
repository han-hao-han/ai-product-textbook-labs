from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.generation_config import (
    installed_generation_dependency_versions,
    load_generation_config,
)
from src.paths import GENERATION_CONFIG_PATH


def test_generation_config_freezes_confirmed_h3方案() -> None:
    config = load_generation_config()

    assert config.base_url == (
        "https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    assert config.model == "qwen3.7-plus-2026-05-26"
    assert config.response_format == {"type": "json_object"}
    assert config.temperature == 0
    assert config.stream is False
    assert config.enable_thinking is False
    assert config.output_token_cap is None
    assert installed_generation_dependency_versions(config) == {
        "openai": "2.46.0",
        "pydantic": "2.13.4",
        "python-dotenv": "1.2.2",
        "streamlit": "1.59.2",
    }


def test_generation_config_rejects_output_token_cap(tmp_path: Path) -> None:
    payload = json.loads(GENERATION_CONFIG_PATH.read_text(encoding="utf-8"))
    payload["request"]["output_token_cap"] = 1400
    path = tmp_path / "generation.json"
    path.write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="方案A"):
        load_generation_config(path)
