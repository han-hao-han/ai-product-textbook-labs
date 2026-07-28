from __future__ import annotations

from pathlib import Path

import pytest

from src.checkpoint_report import write_checkpoint1_report
from src.source_config import load_source_config


def test_checkpoint_report_writes_both_formats(tmp_path: Path) -> None:
    config = load_source_config()

    report_md, report_json = write_checkpoint1_report(
        run_dir=tmp_path,
        config=config,
        status="not_run",
    )

    assert report_md.is_file()
    assert report_json.is_file()
    assert "未调用Embedding模型" in report_md.read_text(encoding="utf-8")


def test_checkpoint_report_rejects_unknown_status(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="无效检查点状态"):
        write_checkpoint1_report(
            run_dir=tmp_path,
            config=load_source_config(),
            status="done",
        )
