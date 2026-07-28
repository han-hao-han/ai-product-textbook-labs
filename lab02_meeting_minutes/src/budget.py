from __future__ import annotations

import json
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
BUDGET_PATH = PROJECT_DIR / "api_call_budget.json"
DEFAULT_BUDGET = {
    "experiment": "1.5.2",
    "limit": 50,
    "used": 0,
    "remaining": 50,
    "warning_threshold": 40,
    "status": "active",
}


def load_budget(path: Path = BUDGET_PATH) -> dict:
    if not path.exists():
        return DEFAULT_BUDGET.copy()
    return json.loads(path.read_text(encoding="utf-8"))


def ensure_budget_available(path: Path = BUDGET_PATH) -> dict:
    budget = load_budget(path)
    if int(budget["remaining"]) <= 0:
        raise RuntimeError("real API call budget is exhausted")
    if int(budget["used"]) >= int(budget["warning_threshold"]):
        raise RuntimeError("real API call budget reached warning threshold")
    return budget


def record_api_call(path: Path = BUDGET_PATH) -> dict:
    budget = load_budget(path)
    budget["used"] = int(budget["used"]) + 1
    budget["remaining"] = int(budget["limit"]) - int(budget["used"])
    if budget["remaining"] <= 0:
        budget["status"] = "exhausted"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(budget, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return budget
