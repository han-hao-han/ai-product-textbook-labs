from __future__ import annotations

import base64
import json
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CASES = {
    "TS3010a": {"domain": "Product", "split": "val", "official_path": "data/Product/val/TS3010a.json", "role": "main"},
    "IS1003a": {"domain": "Product", "split": "test", "official_path": "data/Product/test/IS1003a.json", "role": "curated_sample"},
    "ES2011a": {"domain": "Product", "split": "test", "official_path": "data/Product/test/ES2011a.json", "role": "curated_sample"},
}


def main() -> int:
    manifest = json.loads((ROOT / "external_manifest.json").read_text(encoding="utf-8"))
    case_dir = ROOT / "data" / "selected_cases"
    manifest_dir = ROOT / "data" / "manifests"
    case_dir.mkdir(parents=True, exist_ok=True)
    manifest_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    for case_id, case_config in CASES.items():
        case = next(item for item in manifest["candidate_cases"] if item["case_id"] == case_id)
        if case["official_path"] != case_config["official_path"]:
            raise RuntimeError(f"Case path does not match external_manifest.json: {case_id}")
        payload = _load_official_case(case_config["official_path"])
        transcript_path = case_dir / f"{case_id}.md"
        transcript_path.write_text(_to_markdown(payload, case_id, case_config), encoding="utf-8")
        metadata = {
            "dataset": "QMSum",
            "case_id": case_id,
            "domain": case_config["domain"],
            "split": case_config["split"],
            "official_path": case_config["official_path"],
            "source_repository": "https://github.com/Yale-LILY/QMSum",
            "stored_files": [str(transcript_path.relative_to(ROOT)).replace("\\", "/")],
            "turn_count": len(payload.get("meeting_transcripts", [])),
            "topic_count": len(payload.get("topic_list", [])),
            "general_query_count": len(payload.get("general_query_list", [])),
            "specific_query_count": len(payload.get("specific_query_list", [])),
            "distribution_note": "Only three curated converted transcripts are stored for the addon experiment; the full QMSum dataset is not stored.",
        }
        (manifest_dir / f"{case_id}_manifest.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        results.append(metadata)
    print(json.dumps({"case_count": len(results), "cases": results}, ensure_ascii=False, indent=2))
    return 0


def _load_official_case(official_path: str) -> dict[str, Any]:
    api_url = f"https://api.github.com/repos/Yale-LILY/QMSum/contents/{official_path}"
    with urllib.request.urlopen(api_url, timeout=30) as response:
        content = json.loads(response.read().decode("utf-8"))["content"]
    raw = base64.b64decode("".join(content.split())).decode("utf-8")
    return json.loads(raw)


def _to_markdown(payload: dict[str, Any], case_id: str, case_config: dict[str, str]) -> str:
    lines = [
        f"# qmsum_{case_config['domain'].lower()}_{case_config['split']}_{case_id}",
        "",
        f"数据来源：QMSum {case_config['domain']}/{case_config['split']}",
        f"官方路径：{case_config['official_path']}",
        "说明：这是 1.5.2 附加实验保留的三个审计样例之一，未保存完整 QMSum 数据集。",
        "",
        "## QMSum Topics",
    ]
    for index, topic in enumerate(payload.get("topic_list", []), start=1):
        lines.append(f"{index}. {topic.get('topic', '')}")

    lines.extend(["", "## QMSum General Queries"])
    for item in payload.get("general_query_list", []):
        lines.append(f"- Query: {item.get('query', '')}")

    lines.extend(["", "## QMSum Specific Queries"])
    for item in payload.get("specific_query_list", []):
        lines.append(f"- Query: {item.get('query', '')}")

    lines.extend(["", "## Meeting Transcript"])
    for turn in payload.get("meeting_transcripts", []):
        speaker = str(turn.get("speaker", "")).strip()
        content = " ".join(str(turn.get("content", "")).split())
        lines.append(f"- {speaker}: {content}")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
