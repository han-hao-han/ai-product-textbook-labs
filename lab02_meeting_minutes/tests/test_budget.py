import json
from pathlib import Path

from lab02_meeting_minutes.src.budget import ensure_budget_available, record_api_call


def test_record_api_call_updates_budget(tmp_path: Path) -> None:
    path = tmp_path / "budget.json"
    path.write_text(json.dumps({"experiment": "1.5.2", "limit": 50, "used": 0, "remaining": 50, "warning_threshold": 40, "status": "active"}), encoding="utf-8")
    ensure_budget_available(path)
    updated = record_api_call(path)
    assert updated["used"] == 1
    assert updated["remaining"] == 49
