from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lab02_meeting_minutes.src.gold_compare import compare_gold_file


LAB_DIR = Path(__file__).resolve().parent


def main() -> int:
    checks = [
        _check_required_files(),
        _check_lock_accepted(),
        _check_budget(),
        _check_representative_real_regression(),
        _check_screenshots_manifest(),
        _check_sensitive_text(),
    ]
    payload = {"acceptance_version": "acceptance_v1_h4_final", "ok": all(item["ok"] for item in checks), "checks": checks}
    output = LAB_DIR / "outputs" / "acceptance_report_h4_final.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 2


def _check_required_files() -> dict[str, Any]:
    required = [
        "experiment_lock.json",
        "api_call_budget.json",
        "src/schemas.py",
        "src/prompts.py",
        "src/validators.py",
        "src/gold_compare.py",
        "run_fixed_regression.py",
        "run_acceptance.py",
        "streamlit_app.py",
        "outputs/fixed_regression_real_v11_report.json",
        "evidence/experiment_facts.md",
        "evidence/verified_environment.md",
        "evidence/verified_results.json",
        "evidence/screenshots_manifest.md",
        "evidence/code_snippets_for_textbook.md",
        "evidence/known_limitations.md",
        "evidence/acceptance_report.md",
        "evidence/handoff_summary.md",
    ]
    missing = [path for path in required if not (LAB_DIR / path).exists()]
    return {"name": "required_files", "ok": not missing, "missing": missing}


def _check_lock_accepted() -> dict[str, Any]:
    lock = _read_json(LAB_DIR / "experiment_lock.json")
    required = {
        "status": "accepted",
        "model": "deepseek-v4-flash",
        "prompt_version": "prompt_v11_open_question_precision_guard_h4_dirty",
        "schema_version": "schema_v1_h3_draft",
        "validator_version": "validator_v2_noise_tolerant_evidence",
        "gold_compare_version": "gold_compare_v1_h3_draft",
        "acceptance_version": "acceptance_v1_h4_final",
        "verified_date": "2026-07-20",
    }
    mismatches = {key: {"expected": value, "actual": lock.get(key)} for key, value in required.items() if lock.get(key) != value}
    return {"name": "lock_accepted_versions", "ok": not mismatches, "mismatches": mismatches}


def _check_budget() -> dict[str, Any]:
    budget = _read_json(LAB_DIR / "api_call_budget.json")
    ok = budget.get("used", 0) <= budget.get("limit", 0) and budget.get("remaining", -1) >= 0
    return {"name": "api_budget", "ok": ok, "used": budget.get("used"), "limit": budget.get("limit"), "remaining": budget.get("remaining")}


def _check_representative_real_regression() -> dict[str, Any]:
    report = _read_json(LAB_DIR / "outputs" / "fixed_regression_real_v11_report.json")
    main_result = LAB_DIR / "outputs" / "fixed_regression" / "real" / "meeting_main_001.json"
    compare_report = compare_gold_file(LAB_DIR / "data" / "gold" / "main_gold.json", main_result)
    ok = report.get("ok") is True and compare_report.ok
    return {
        "name": "representative_real_regression_v11",
        "ok": ok,
        "case_count": report.get("case_count"),
        "report_ok": report.get("ok"),
        "main_gold_compare_ok": compare_report.ok,
        "gold_compare_issue_count": len(compare_report.issues),
    }


def _check_sensitive_text() -> dict[str, Any]:
    patterns = [re.compile(r"sk-[A-Za-z0-9_-]{12,}"), re.compile(r"Bearer\s+[A-Za-z0-9._-]{12,}", re.IGNORECASE)]
    hits: list[str] = []
    for path in LAB_DIR.rglob("*"):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        if path.suffix.lower() not in {".py", ".json", ".md", ".txt", ".example"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if any(pattern.search(text) for pattern in patterns):
            hits.append(str(path.relative_to(LAB_DIR)))
    return {"name": "sensitive_text_scan", "ok": not hits, "hits": hits}


def _check_screenshots_manifest() -> dict[str, Any]:
    manifest = LAB_DIR / "evidence" / "screenshots_manifest.md"
    screenshot_dir = LAB_DIR / "screenshots"
    png_count = len(list(screenshot_dir.glob("*.png"))) if screenshot_dir.exists() else 0
    return {"name": "screenshots_manifest", "ok": manifest.exists() and png_count > 0, "manifest_exists": manifest.exists(), "png_count": png_count}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
