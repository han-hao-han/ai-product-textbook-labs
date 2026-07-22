from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lab02_meeting_minutes.src.config import load_settings, validate_real_api_settings
from lab02_meeting_minutes.src.gold_compare import compare_gold_file
from lab02_meeting_minutes.src.pipeline import run_mock_pipeline, run_real_pipeline


LAB_DIR = Path(__file__).resolve().parent
DATA_DIR = LAB_DIR / "data"
GOLD_BY_GROUP = {
    "main": DATA_DIR / "gold" / "main_gold.json",
    "demo": DATA_DIR / "gold" / "demo_gold.json",
    "regression": DATA_DIR / "gold" / "regression_gold.json",
    "edge": DATA_DIR / "gold" / "edge_gold.json",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run fixed Lab 1.5.2 regression cases")
    parser.add_argument("--mode", choices=["mock", "real"], default="mock")
    parser.add_argument("--cases", nargs="*", help="Case ids to run. Omit for all cases in mock mode.")
    parser.add_argument("--output-dir", type=Path, default=LAB_DIR / "outputs" / "fixed_regression")
    parser.add_argument("--report", type=Path, default=LAB_DIR / "outputs" / "fixed_regression_report.json")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    settings = load_settings()
    if args.mode == "real":
        validate_real_api_settings(settings)
    cases = _select_cases(args.cases)
    if args.mode == "real" and not args.cases:
        raise ValueError("real mode requires explicit --cases to control API budget")

    report_items: list[dict[str, Any]] = []
    for case in cases:
        output_path = args.output_dir / args.mode / f"{case['meeting_id']}.json"
        runner = run_real_pipeline if args.mode == "real" else run_mock_pipeline
        result = runner(case["path"], output_path, settings, force_mode="single_pass")
        compare_report = compare_gold_file(case["gold_path"], output_path)
        report_items.append(
            {
                "meeting_id": case["meeting_id"],
                "group": case["group"],
                "mode": args.mode,
                "result_path": str(output_path),
                "validation_issue_count": len(result.validation_issues),
                "gold_compare_ok": compare_report.ok,
                "gold_compare_issues": [issue.__dict__ for issue in compare_report.issues],
            }
        )

    payload = {
        "mode": args.mode,
        "case_count": len(report_items),
        "ok": all(item["validation_issue_count"] == 0 and item["gold_compare_ok"] for item in report_items),
        "items": report_items,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 2


def _select_cases(case_ids: list[str] | None) -> list[dict[str, Any]]:
    available = _available_cases()
    if not case_ids:
        return available
    by_id = {case["meeting_id"]: case for case in available}
    missing = [case_id for case_id in case_ids if case_id not in by_id]
    if missing:
        raise ValueError(f"unknown case ids: {', '.join(missing)}")
    return [by_id[case_id] for case_id in case_ids]


def _available_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for group in ["main", "demo", "regression", "edge"]:
        for path in sorted((DATA_DIR / group).glob("*.md")):
            cases.append({"meeting_id": path.stem, "group": group, "path": path, "gold_path": GOLD_BY_GROUP[group]})
    return cases


if __name__ == "__main__":
    raise SystemExit(main())
