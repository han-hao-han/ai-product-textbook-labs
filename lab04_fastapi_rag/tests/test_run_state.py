from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.run_state import initialize_run, make_run_id, validate_run_id
from src.source_config import load_source_config


def test_run_id_format() -> None:
    run_id = make_run_id(datetime(2026, 7, 27, 12, 34, 56, tzinfo=timezone.utc))

    assert run_id.startswith("fastapi_rag_20260727_123456_")
    assert validate_run_id(run_id) == run_id


def test_invalid_run_id_is_rejected() -> None:
    with pytest.raises(ValueError, match="experiment_run_id"):
        validate_run_id("../unsafe")


def test_initialize_run_is_non_overwriting(tmp_path: Path) -> None:
    config = load_source_config()
    run_id = "fastapi_rag_20260727_123456_abcdef"
    config_path = Path("configs/source_config.json")

    run_dir = initialize_run(
        config=config,
        run_id=run_id,
        device="cpu",
        runs_dir=tmp_path,
        config_path=config_path,
    )

    assert (run_dir / "manifest.json").is_file()
    assert (run_dir / "environment_precheck.json").is_file()
    assert (
        run_dir / "config_snapshot" / "embedding_config.json"
    ).is_file()
    assert (run_dir / "source").is_dir()
    assert (run_dir / "checkpoints").is_dir()
    with pytest.raises(FileExistsError, match="拒绝覆盖"):
        initialize_run(
            config=config,
            run_id=run_id,
            device="cpu",
            runs_dir=tmp_path,
            config_path=config_path,
        )
