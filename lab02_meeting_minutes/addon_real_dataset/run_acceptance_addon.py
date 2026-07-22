from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    checks = [
        _check_required_files(),
        _check_lock_acceptance_ready(),
        _check_v2_result(),
        _check_v2_gold_compare(),
        _check_data_scope(),
        _check_api_budget(),
        _check_sensitive_text(),
    ]
    payload = {"acceptance_version": "addon_acceptance_v1_h4_candidate", "ok": all(item["ok"] for item in checks), "checks": checks}
    output = ROOT / "outputs" / "addon_acceptance_report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 2


def _check_required_files() -> dict[str, Any]:
    required = [
        "README.md",
        "addon_lock.json",
        "external_manifest.json",
        "h1_qmsum_data_audit.md",
        "h2_sample_candidates.md",
        "h2_gold_standard_review.md",
        "h3_architecture_schema_prompt_validation.md",
        "h4_real_smoke_review.md",
        "addon_prompt_qmsum_v1.md",
        "data/selected_cases/TS3010a.md",
        "data/selected_cases/IS1003a.md",
        "data/selected_cases/ES2011a.md",
        "data/manifests/TS3010a_manifest.json",
        "data/manifests/IS1003a_manifest.json",
        "data/manifests/ES2011a_manifest.json",
        "data/gold/TS3010a_gold.json",
        "scripts/fetch_qmsum_case.py",
        "scripts/qmsum_local_dataset.py",
        "scripts/qmsum_pipeline.py",
        "scripts/run_qmsum_smoke.py",
        "scripts/repair_qmsum_smoke_output.py",
        "scripts/compare_qmsum_gold.py",
        "outputs/real_smoke/TS3010a_v2_result.json",
        "outputs/real_smoke/TS3010a_v2_metadata.json",
        "outputs/real_smoke/TS3010a_v2_gold_compare.json",
        "evidence/experiment_facts.md",
        "evidence/verified_results.json",
        "evidence/acceptance_report.md",
        "evidence/known_limitations.md",
        "evidence/handoff_summary.md",
    ]
    missing = [path for path in required if not (ROOT / path).exists()]
    return {"name": "required_files", "ok": not missing, "missing": missing}


def _check_lock_acceptance_ready() -> dict[str, Any]:
    lock = _read_json(ROOT / "addon_lock.json")
    expected = {
        "h0_confirmed": True,
        "h1_status": "confirmed",
        "h2_status": "confirmed",
        "h3_status": "confirmed",
        "h4_smoke_status": "acceptance_ready",
        "selected_case_id": "TS3010a",
        "prompt_version": "addon_prompt_qmsum_real_meeting_v4_owner_decision_precision",
        "validator_version": "validator_v2_noise_tolerant_evidence_reused_with_addon_notes",
        "full_dataset_policy": "optional_local_download_to_ignored_cache",
    }
    mismatches = {key: {"expected": value, "actual": lock.get(key)} for key, value in expected.items() if lock.get(key) != value}
    curated_ok = lock.get("curated_sample_ids") == ["TS3010a", "IS1003a", "ES2011a"]
    return {"name": "lock_acceptance_ready", "ok": not mismatches and curated_ok, "mismatches": mismatches, "curated_sample_ids": lock.get("curated_sample_ids")}


def _check_v2_result() -> dict[str, Any]:
    result = _read_json(ROOT / "outputs" / "real_smoke" / "TS3010a_v2_result.json")
    action_count = len(result.get("action_items", []))
    question_count = len(result.get("open_questions", []))
    issue_count = len(result.get("validation_issues", []))
    decision_count = len(result.get("decisions", []))
    ok = issue_count == 0 and action_count == 0 and question_count == 0 and decision_count >= 8
    return {
        "name": "v2_result_structure",
        "ok": ok,
        "validation_issue_count": issue_count,
        "decision_count": decision_count,
        "action_item_count": action_count,
        "open_question_count": question_count,
    }


def _check_v2_gold_compare() -> dict[str, Any]:
    report = _read_json(ROOT / "outputs" / "real_smoke" / "TS3010a_v2_gold_compare.json")
    return {
        "name": "v2_gold_compare",
        "ok": report.get("ok") is True and report.get("recalled_decision_count") == report.get("expected_decision_count") == 8,
        "expected_decision_count": report.get("expected_decision_count"),
        "recalled_decision_count": report.get("recalled_decision_count"),
        "issue_count": len(report.get("issues", [])),
    }


def _check_data_scope() -> dict[str, Any]:
    selected = sorted(path.name for path in (ROOT / "data" / "selected_cases").glob("*.md"))
    expected = ["ES2011a.md", "IS1003a.md", "TS3010a.md"]
    original_json_files = [
        str(path.relative_to(ROOT))
        for path in (ROOT / "data").rglob("*.json")
        if "gold" not in path.parts and "manifests" not in path.parts and "downloads" not in path.parts
    ]
    gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8", errors="ignore")
    ignore_ok = "**/data/downloads/" in gitignore and "lab02_meeting_minutes/outputs/streamlit_runs/" in gitignore
    ok = selected == expected and not original_json_files and ignore_ok
    return {
        "name": "data_scope_three_curated_samples_and_local_download_cache",
        "ok": ok,
        "selected_cases": selected,
        "unexpected_original_json_files": original_json_files,
        "local_cache_ignore_ok": ignore_ok,
    }


def _check_api_budget() -> dict[str, Any]:
    path = PROJECT_ROOT / "lab02_meeting_minutes" / "api_call_budget.json"
    if not path.exists():
        return {"name": "api_budget_local_optional", "ok": True, "status": "not_committed"}
    budget = _read_json(path)
    used = int(budget.get("used", 0))
    limit = int(budget.get("limit", 0))
    remaining = int(budget.get("remaining", -1))
    ok = used >= 30 and used <= limit and remaining == limit - used and used < int(budget.get("warning_threshold", limit + 1))
    return {"name": "api_budget_local_optional", "ok": ok, "status": "present", "used": used, "remaining": remaining, "limit": limit}


def _check_sensitive_text() -> dict[str, Any]:
    patterns = [re.compile(r"sk-[A-Za-z0-9_-]{12,}"), re.compile(r"Bearer\s+[A-Za-z0-9._-]{12,}", re.IGNORECASE)]
    hits: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        if path.suffix.lower() not in {".py", ".json", ".md", ".txt", ".example"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if any(pattern.search(text) for pattern in patterns):
            hits.append(str(path.relative_to(ROOT)))
    return {"name": "sensitive_text_scan", "ok": not hits, "hits": hits}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
