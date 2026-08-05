"""Saved-response audit for the three V3 terminal failure classes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.claim_level_report_controller_v3_1 import (
    CHART_TITLE_TEMPLATES,
    INTERPRETATION_TEMPLATES,
    RECOMMENDATION_TEMPLATES,
    REPORT_TITLE_TEMPLATES,
)


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"saved case is not an object: {path}")
    return value


def validate_v3_1_saved_response_regression(
    *, old_cases: dict[str, Path], v3_1_cases: dict[str, Path]
) -> dict[str, Any]:
    expected = {"Q02", "Q04", "Q05"}
    if set(old_cases) != expected or set(v3_1_cases) != expected:
        raise ValueError("saved regression requires exactly Q02, Q04 and Q05")
    allowed_chart_titles = {
        title for templates in CHART_TITLE_TEMPLATES.values() for title in templates.values()
    }
    case_results = []
    for question_id in sorted(expected):
        old = _load(old_cases[question_id])
        current = _load(v3_1_cases[question_id])
        old_failed = old.get("program_status") == "failed"
        traces = current.get("terminal_protocol_trace", [])
        current_passed = (
            current.get("program_status") == "passed_deterministic_pending_manual_review"
            and traces
            and traces[-1].get("status") == "passed"
        )
        parsed = traces[-1].get("parsed_model_response", {}) if traces else {}
        mapped = traces[-1].get("mapped_program_response", {}) if traces else {}
        report = mapped.get("report", {})
        sections = report.get("sections", [])
        controlled_surface = (
            "title" not in parsed
            and "chart_titles" not in parsed
            and len(parsed.get("template_selections", [])) == 2
            and report.get("title") in REPORT_TITLE_TEMPLATES.values()
            and len(sections) == 6
            and sections[3]["claims"][0]["statement"] in INTERPRETATION_TEMPLATES.values()
            and sections[4]["claims"][0]["statement"] in RECOMMENDATION_TEMPLATES.values()
            and all(
                item.get("title") in allowed_chart_titles
                for item in mapped.get("chart_requests", [])
            )
        )
        case_results.append(
            {
                "question_id": question_id,
                "old_v3_failure_preserved": old_failed,
                "v3_1_case_passed": current_passed,
                "controlled_text_surface": controlled_surface,
            }
        )
    passed = all(
        item["old_v3_failure_preserved"]
        and item["v3_1_case_passed"]
        and item["controlled_text_surface"]
        for item in case_results
    )
    return {
        "schema_version": "1.5.6-h3-claim-controller-v3-1-saved-response-regression-v1",
        "status": "passed" if passed else "failed",
        "cases": case_results,
        "real_model_called": False,
        "old_responses_modified": False,
    }


__all__ = ["validate_v3_1_saved_response_regression"]
