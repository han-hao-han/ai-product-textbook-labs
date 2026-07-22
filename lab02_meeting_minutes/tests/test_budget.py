import json
from pathlib import Path

from lab02_meeting_minutes.src.budget import ensure_budget_available, load_budget, record_api_call


def test_record_api_call_updates_budget(tmp_path: Path) -> None:
    path = tmp_path / "budget.json"
    path.write_text(json.dumps({"experiment": "1.5.2", "limit": 50, "used": 0, "remaining": 50, "warning_threshold": 40, "status": "active"}), encoding="utf-8")
    ensure_budget_available(path)
    updated = record_api_call(path)
    assert updated["used"] == 1
    assert updated["remaining"] == 49


def test_missing_budget_uses_local_default_without_creating_file(tmp_path: Path) -> None:
    path = tmp_path / "missing_budget.json"
    budget = load_budget(path)
    assert budget["experiment"] == "1.5.2"
    assert budget["used"] == 0
    assert budget["remaining"] == budget["limit"]
    assert not path.exists()
