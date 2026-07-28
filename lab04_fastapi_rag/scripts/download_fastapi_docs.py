from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.downloader import DownloadError, download_and_extract  # noqa: E402
from src.run_state import require_compatible_run, resolve_run_dir  # noqa: E402
from src.source_config import load_source_config  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="从FastAPI官方GitHub地址下载并核验固定Commit ZIP。"
    )
    parser.add_argument("--experiment-run-id", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print("[检查点1/步骤1] 下载FastAPI固定版本中文文档")
    try:
        config = load_source_config()
        run_dir = resolve_run_dir(args.experiment_run_id)
        require_compatible_run(run_dir, config)
        metadata = download_and_extract(run_dir, config)
    except (
        DownloadError,
        FileExistsError,
        FileNotFoundError,
        OSError,
        RuntimeError,
        ValueError,
    ) as error:
        print(f"文档下载失败：{type(error).__name__}: {error}", file=sys.stderr)
        print("未进入文档检查；请保留错误信息并检查网络、Commit和运行ID。")
        return 1

    print(f"官方仓库：{metadata['repository']}")
    print(f"Release：{metadata['release_tag']}")
    print(f"Commit：{metadata['commit']}")
    print(f"ZIP大小：{metadata['archive_bytes']} bytes")
    print(f"ZIP SHA-256：{metadata['archive_sha256']}")
    print(f"ZIP成员数：{metadata['zip_member_count']}")
    print(f"下载尝试次数：{metadata['response']['attempt_count']}")
    print("许可证核验：MIT，Git blob SHA-1匹配")
    print("生成文件：source/download.json")
    print("下一步：")
    print(
        "python scripts/inspect_documents.py "
        f"--experiment-run-id {run_dir.name}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
