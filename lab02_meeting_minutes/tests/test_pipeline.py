from pathlib import Path

from lab02_meeting_minutes.src.config import load_settings
from lab02_meeting_minutes.src.pipeline import run_mock_pipeline


def test_mock_pipeline_saves_main_result(tmp_path: Path) -> None:
    output = tmp_path / "main_result.json"
    result = run_mock_pipeline(Path("lab02_meeting_minutes/data/main/meeting_main_001.md"), output, load_settings(), force_mode="single_pass")
    assert output.exists()
    assert result.meeting_id == "meeting_main_001"
    assert result.action_items[0].due_date_normalized == "2026-07-24"
    assert result.processing_metadata.model == "mock"
    assert result.validation_issues == []


def test_mock_pipeline_does_not_normalize_without_meeting_date(tmp_path: Path) -> None:
    output = tmp_path / "edge_result.json"
    result = run_mock_pipeline(Path("lab02_meeting_minutes/data/edge/edge_003_relative_no_meeting_date.md"), output, load_settings(), force_mode="single_pass")
    assert result.action_items[0].due_date_raw == "下周三前"
    assert result.action_items[0].due_date_normalized is None
