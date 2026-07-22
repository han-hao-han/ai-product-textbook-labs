from __future__ import annotations

import json
import sys
from argparse import ArgumentParser
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    parser = ArgumentParser()
    parser.add_argument("--prompt", choices=["v1", "v2"], default="v2")
    args = parser.parse_args()
    gold_path = ROOT / "data" / "gold" / "TS3010a_gold.json"
    result_path = ROOT / "outputs" / "real_smoke" / f"TS3010a_{args.prompt}_result.json"
    report_path = ROOT / "outputs" / "real_smoke" / f"TS3010a_{args.prompt}_gold_compare.json"
    report = compare_files(gold_path, result_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 2


def compare_files(gold_path: Path, result_path: Path) -> dict[str, Any]:
    gold = json.loads(gold_path.read_text(encoding="utf-8"))
    result = json.loads(result_path.read_text(encoding="utf-8"))
    issues: list[dict[str, Any]] = []

    result_action_items = result.get("action_items", [])
    if gold.get("expected_action_items", []) == [] and result_action_items:
        issues.append({"kind": "action_items", "code": "unexpected_action_items", "count": len(result_action_items)})

    result_open_questions = result.get("open_questions", [])
    if gold.get("expected_open_questions", []) == [] and result_open_questions:
        issues.append({"kind": "open_questions", "code": "unexpected_open_questions", "count": len(result_open_questions)})

    result_decision_text = _combined_text(result.get("decisions", []), ["decision", "evidence"])
    recalled: list[str] = []
    for item in gold.get("expected_decisions", []):
        anchors = [str(anchor).lower() for anchor in item.get("semantic_anchors", [])]
        missing = [anchor for anchor in anchors if anchor not in result_decision_text]
        if missing:
            issues.append(
                {
                    "kind": "decisions",
                    "code": "missing_design_requirement",
                    "decision_id": item.get("decision_id"),
                    "missing_anchors": missing,
                    "gold_decision": item.get("decision"),
                }
            )
        else:
            recalled.append(item.get("decision_id"))

    return {
        "gold_compare_version": "addon_qmsum_gold_compare_v1",
        "ok": not issues,
        "expected_decision_count": len(gold.get("expected_decisions", [])),
        "recalled_decision_count": len(recalled),
        "recalled_decision_ids": recalled,
        "issues": issues,
    }


def _combined_text(items: list[dict[str, Any]], fields: list[str]) -> str:
    parts: list[str] = []
    for item in items:
        for field in fields:
            parts.append(str(item.get(field, "")))
    return " ".join(parts).lower()


if __name__ == "__main__":
    raise SystemExit(main())
