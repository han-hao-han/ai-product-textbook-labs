from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .validators import extract_speaker_names


class MockLLMClient:
    """Deterministic stand-in for the real model during local chain tests."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir

    def extract(self, meeting_id: str, meeting_text: str, meeting_date: str | None) -> dict[str, Any]:
        if meeting_id == "meeting_main_001":
            return self._main_response(meeting_date)
        return self._collection_response(meeting_id, meeting_text, meeting_date)

    def _main_response(self, meeting_date: str | None) -> dict[str, Any]:
        gold = json.loads((self.data_dir / "gold" / "main_gold.json").read_text(encoding="utf-8"))
        return {
            "meeting_id": gold["meeting_id"],
            "meeting_title": gold["meeting_title"],
            "meeting_date": meeting_date,
            "attendees": gold["attendees"],
            "topics": gold["topics"],
            "decisions": gold["decisions"],
            "action_items": [_strip_normalized_date(item) for item in gold["action_items"]],
            "open_questions": gold["open_questions"],
            "meeting_summary": gold["meeting_summary"],
        }

    def _collection_response(self, meeting_id: str, meeting_text: str, meeting_date: str | None) -> dict[str, Any]:
        case = self._find_case(meeting_id)
        attendees = [{"name": name, "role": None, "evidence": f"{name}："} for name in sorted(extract_speaker_names(meeting_text))]
        return {
            "meeting_id": meeting_id,
            "meeting_title": meeting_id,
            "meeting_date": meeting_date,
            "attendees": attendees,
            "topics": [],
            "decisions": [{"decision_id": f"D{index:03d}", **item} for index, item in enumerate(case.get("expected_decisions", []), start=1)],
            "action_items": [{"action_id": f"A{index:03d}", "status": "pending", **_strip_normalized_date(item)} for index, item in enumerate(case.get("expected_action_items", []), start=1)],
            "open_questions": [{"question_id": f"Q{index:03d}", "owner": None, **item} for index, item in enumerate(case.get("expected_open_questions", []), start=1)],
            "meeting_summary": "Mock 摘要：用于本地链路验证，不作为真实模型结果。",
        }

    def _find_case(self, meeting_id: str) -> dict[str, Any]:
        for filename in ["demo_gold.json", "regression_gold.json", "edge_gold.json"]:
            gold = json.loads((self.data_dir / "gold" / filename).read_text(encoding="utf-8"))
            for case in gold["cases"]:
                if case["meeting_id"] == meeting_id:
                    return case
        raise ValueError(f"no mock gold case found for meeting_id: {meeting_id}")


def _strip_normalized_date(item: dict[str, Any]) -> dict[str, Any]:
    result = dict(item)
    result["due_date_normalized"] = None
    return result
