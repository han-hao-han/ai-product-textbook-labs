from __future__ import annotations

import json
import shutil
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DOWNLOAD_DIR = ROOT / "data" / "downloads"
CACHE_DIR = DOWNLOAD_DIR / "qmsum_full"
ARCHIVE_PATH = DOWNLOAD_DIR / "qmsum_main.zip"
QMSUM_ZIP_URL = "https://codeload.github.com/Yale-LILY/QMSum/zip/refs/heads/main"
DOMAINS = {"Academic", "Product", "Committee"}
SPLITS = {"train", "val", "test"}


@dataclass(frozen=True)
class QMSumCase:
    case_id: str
    domain: str
    split: str
    path: Path
    label: str


def dataset_is_downloaded(cache_dir: Path = CACHE_DIR) -> bool:
    return (cache_dir / "data").exists() and bool(list_qmsum_cases(cache_dir))


def download_qmsum_dataset(cache_dir: Path = CACHE_DIR, archive_path: Path = ARCHIVE_PATH) -> dict[str, Any]:
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(QMSUM_ZIP_URL, timeout=120) as response:
        archive_path.write_bytes(response.read())

    data_root = cache_dir / "data"
    if data_root.exists():
        shutil.rmtree(data_root)
    data_root.mkdir(parents=True, exist_ok=True)

    extracted = 0
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            parts = Path(member.filename).parts
            if len(parts) < 3 or parts[1] != "data":
                continue
            relative = Path(*parts[1:])
            target = cache_dir / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, target.open("wb") as destination:
                shutil.copyfileobj(source, destination)
            extracted += 1

    cases = list_qmsum_cases(cache_dir)
    metadata = {
        "source": "https://github.com/Yale-LILY/QMSum",
        "download_url": QMSUM_ZIP_URL,
        "cache_dir": str(cache_dir),
        "data_files_extracted": extracted,
        "case_count": len(cases),
    }
    (cache_dir / "download_manifest.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata


def list_qmsum_cases(cache_dir: Path = CACHE_DIR) -> list[QMSumCase]:
    data_root = cache_dir / "data"
    if not data_root.exists():
        return []
    cases: list[QMSumCase] = []
    for domain in sorted(DOMAINS):
        for split in sorted(SPLITS):
            split_dir = data_root / domain / split
            if not split_dir.exists():
                continue
            for path in sorted(split_dir.glob("*.json")):
                case_id = path.stem
                cases.append(QMSumCase(case_id=case_id, domain=domain, split=split, path=path, label=f"{domain}/{split}/{path.name}"))
    return cases


def load_case(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def convert_case_to_markdown(payload: dict[str, Any], domain: str, split: str, case_id: str, source_path: str) -> str:
    lines = [
        f"# qmsum_{domain.lower()}_{split}_{case_id}",
        "",
        f"数据来源：QMSum {domain}/{split}",
        f"本地路径：{source_path}",
        "说明：这是从用户本地 QMSum 完整数据缓存中选择的样例；完整数据集不写入仓库。",
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


def write_converted_case(case: QMSumCase, output_dir: Path) -> Path:
    payload = load_case(case.path)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"qmsum_{case.domain.lower()}_{case.split}_{case.case_id}.md"
    output_path.write_text(convert_case_to_markdown(payload, case.domain, case.split, case.case_id, str(case.path)), encoding="utf-8")
    return output_path
