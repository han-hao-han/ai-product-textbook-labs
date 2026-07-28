from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.source_config import load_source_config


def test_frozen_source_contract() -> None:
    config = load_source_config()

    assert config.schema_version == "fastapi_source_v4"
    assert config.release_tag == "0.136.3"
    assert config.commit == "82064857539e6286522c347b4b11331b48dd2378"
    assert config.expected_included_pages == 102
    assert config.included_groups == {
        "tutorial": 50,
        "advanced": 34,
        "deployment": 7,
        "how-to": 11,
    }
    assert len(config.excluded_pages) == 3
    assert len(config.code_dependency_exceptions) == 1
    exception = config.code_dependency_exceptions[0]
    assert exception.source_path == (
        "docs/zh/docs/how-to/configure-swagger-ui.md"
    )
    assert exception.dependency_path == "fastapi/openapi/docs.py"
    assert exception.line_selection == (9, 24)
    assert exception.expected_occurrences == 1
    assert config.chunking.strategy == "heading_aware_adjacent_merge_v1"
    assert config.commit in config.archive_url


def test_invalid_commit_is_rejected(tmp_path: Path) -> None:
    original = json.loads(
        Path("configs/source_config.json").read_text(encoding="utf-8")
    )
    original["commit"] = "master"
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(original), encoding="utf-8")

    with pytest.raises(ValueError, match="40位"):
        load_source_config(path)
