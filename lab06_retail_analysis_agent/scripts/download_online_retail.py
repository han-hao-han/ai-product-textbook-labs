"""Download the frozen UCI Online Retail dataset from its official source."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOWNLOAD_DIR = PROJECT_ROOT / "data" / "downloads"
RAW_DIR = PROJECT_ROOT / "data" / "raw"
ARCHIVE_PATH = DOWNLOAD_DIR / "online_retail.zip"
WORKBOOK_PATH = RAW_DIR / "Online Retail.xlsx"
METADATA_PATH = RAW_DIR / "download_metadata.json"

DATASET_PAGE = "https://archive.ics.uci.edu/dataset/352/online+retail"
DOWNLOAD_URL = (
    "https://archive.ics.uci.edu/static/public/352/online%2Bretail.zip"
)
DOI = "10.24432/C5BW33"
LICENSE = "CC BY 4.0"
EXPECTED_MEMBER = "Online Retail.xlsx"
EXPECTED_WORKBOOK_SHA256 = (
    "43465a06f2ccf7c8b5bd2892bc7defb52f97487934fe93b16ae4c3936424676d"
)


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        while chunk := file_handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def download_archive(timeout_seconds: int) -> str:
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    temporary_path = ARCHIVE_PATH.with_suffix(".zip.part")
    request = urllib.request.Request(
        DOWNLOAD_URL,
        headers={"User-Agent": "ai-product-textbook-labs/1.5.6"},
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            final_url = response.geturl()
            with temporary_path.open("wb") as output_file:
                shutil.copyfileobj(response, output_file)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        if temporary_path.exists():
            temporary_path.unlink()
        raise RuntimeError(f"下载UCI数据失败：{exc}") from exc

    temporary_path.replace(ARCHIVE_PATH)
    return final_url


def extract_workbook() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    temporary_path = WORKBOOK_PATH.with_suffix(".xlsx.part")
    try:
        with zipfile.ZipFile(ARCHIVE_PATH) as archive:
            bad_member = archive.testzip()
            if bad_member is not None:
                raise RuntimeError(f"ZIP校验失败，首个损坏成员：{bad_member}")
            if EXPECTED_MEMBER not in archive.namelist():
                members = "、".join(archive.namelist())
                raise RuntimeError(
                    f"ZIP中找不到{EXPECTED_MEMBER}；实际成员：{members}"
                )
            with archive.open(EXPECTED_MEMBER) as source_file:
                with temporary_path.open("wb") as output_file:
                    shutil.copyfileobj(source_file, output_file)
    except (zipfile.BadZipFile, OSError) as exc:
        if temporary_path.exists():
            temporary_path.unlink()
        raise RuntimeError(f"无法解压UCI数据：{exc}") from exc

    actual_hash = sha256_file(temporary_path)
    if actual_hash != EXPECTED_WORKBOOK_SHA256:
        temporary_path.unlink()
        raise RuntimeError(
            "XLSX SHA-256与固定数据清单不一致。"
            f"期望：{EXPECTED_WORKBOOK_SHA256}；实际：{actual_hash}。"
            "请停止并重新核验UCI来源。"
        )

    temporary_path.replace(WORKBOOK_PATH)


def verify_existing_workbook() -> None:
    actual_hash = sha256_file(WORKBOOK_PATH)
    if actual_hash != EXPECTED_WORKBOOK_SHA256:
        raise RuntimeError(
            "已有XLSX SHA-256与固定数据清单不一致。"
            f"期望：{EXPECTED_WORKBOOK_SHA256}；实际：{actual_hash}。"
            "如需重新下载，请先确认后使用--force。"
        )


def save_metadata(final_url: str, reused_download: bool) -> None:
    metadata = {
        "dataset_name": "Online Retail",
        "uci_dataset_id": 352,
        "doi": DOI,
        "license": LICENSE,
        "dataset_page": DATASET_PAGE,
        "requested_download_url": DOWNLOAD_URL,
        "final_download_url": final_url,
        "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
        "reused_existing_archive": reused_download,
        "archive": {
            "relative_path": "data/downloads/online_retail.zip",
            "size_bytes": ARCHIVE_PATH.stat().st_size,
            "sha256": sha256_file(ARCHIVE_PATH),
        },
        "workbook": {
            "relative_path": "data/raw/Online Retail.xlsx",
            "size_bytes": WORKBOOK_PATH.stat().st_size,
            "sha256": sha256_file(WORKBOOK_PATH),
        },
    }
    temporary_path = METADATA_PATH.with_suffix(".json.tmp")
    temporary_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary_path.replace(METADATA_PATH)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="从UCI官方来源下载Online Retail（ID 352）。"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="重新下载并覆盖已有本地原始文件。",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="网络超时秒数，默认120。",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.timeout <= 0:
        print("错误：--timeout必须为正整数。", file=sys.stderr)
        return 2

    reused_download = ARCHIVE_PATH.is_file() and not args.force
    final_url = DOWNLOAD_URL

    try:
        if reused_download:
            print(f"复用已有ZIP：{ARCHIVE_PATH}")
        else:
            print(f"官方来源：{DATASET_PAGE}")
            print(f"正在下载：{DOWNLOAD_URL}")
            final_url = download_archive(args.timeout)

        if WORKBOOK_PATH.is_file() and not args.force:
            print(f"复用已有XLSX：{WORKBOOK_PATH}")
            verify_existing_workbook()
        else:
            extract_workbook()

        save_metadata(final_url, reused_download)
    except RuntimeError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    print("下载与解压完成。")
    print(f"原始文件：{WORKBOOK_PATH}")
    print(f"本地元数据：{METADATA_PATH}")
    print(f"XLSX SHA-256：{sha256_file(WORKBOOK_PATH)}")
    print("下一步：python scripts/inspect_online_retail.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
