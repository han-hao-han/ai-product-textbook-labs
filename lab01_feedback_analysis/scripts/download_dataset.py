from __future__ import annotations

import hashlib
import shutil
import urllib.request
from pathlib import Path


SOURCE_REPOSITORY = "Meituan-Dianping/asap"
SOURCE_COMMIT = "975122a60065240124df62cb4d5dbfd19ed9ef2c"

DATA_FILES = ("train.csv", "dev.csv", "test.csv")

PROJECT_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_DIR / "data" / "raw"

BASE_URL = (
    "https://raw.githubusercontent.com/"
    f"{SOURCE_REPOSITORY}/{SOURCE_COMMIT}/data"
)


def calculate_sha256(file_path: Path) -> str:
    """计算文件的 SHA-256。"""
    digest = hashlib.sha256()

    with file_path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def download_file(filename: str) -> Path:
    """下载一个数据文件，并使用临时文件避免残缺文件被误用。"""
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    target_path = RAW_DIR / filename
    temporary_path = RAW_DIR / f"{filename}.part"
    source_url = f"{BASE_URL}/{filename}"

    request = urllib.request.Request(
        source_url,
        headers={"User-Agent": "ai-product-textbook-lab"},
    )

    print(f"正在下载：{filename}")

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            with temporary_path.open("wb") as output_file:
                shutil.copyfileobj(response, output_file)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise

    temporary_path.replace(target_path)
    return target_path


def main() -> None:
    print(f"数据来源：{SOURCE_REPOSITORY}")
    print(f"固定提交：{SOURCE_COMMIT}")
    print(f"保存目录：{RAW_DIR}")
    print()

    for filename in DATA_FILES:
        file_path = download_file(filename)
        file_size = file_path.stat().st_size
        file_hash = calculate_sha256(file_path)

        print(f"下载完成：{file_path.name}")
        print(f"文件大小：{file_size} bytes")
        print(f"SHA-256：{file_hash}")
        print()

    print("ASAP_DATA_DOWNLOAD_OK")


if __name__ == "__main__":
    main()