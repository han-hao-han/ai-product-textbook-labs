from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.paths import CONFIG_PATH, RAW_DATA_DIR  # noqa: E402
from src.xfund_download import DownloadError, prepare_split  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="从官方GitHub Release准备XFUND v1.0中文数据"
    )
    parser.add_argument(
        "--split",
        choices=("train", "val", "all"),
        default="train",
        help="检查点1只需train；后续固定验证准备时再使用val或all",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="单次网络读取超时秒数，默认60",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    splits = ("train", "val") if args.split == "all" else (args.split,)
    print("[阶段2] XFUND中文真实数据准备")
    print("读者学习目标：观察官方图片、原始标注和显式键值关系。")
    print("来源：https://github.com/doc-analysis/XFUND/releases/tag/v1.0")
    print("许可：CC BY-NC-SA 4.0，仅用于已确认的非商业教学用途。")
    print(f"本地目录：{RAW_DATA_DIR}")

    def show_progress(name: str, downloaded: int, total: int) -> None:
        if downloaded == total or downloaded % (16 * 1024 * 1024) < 1024 * 1024:
            percent = downloaded / total * 100 if total else 0
            print(f"  {name}: {downloaded}/{total} 字节（{percent:.1f}%）")

    try:
        for split in splits:
            print(f"正在准备分组：{split}")
            result = prepare_split(
                split,
                config_path=CONFIG_PATH,
                raw_dir=RAW_DATA_DIR,
                timeout_seconds=args.timeout,
                progress=show_progress,
            )
            print(
                f"完成：{result['annotation']['name']}、"
                f"{result['images']['name']}、"
                f"解压目录{result['extraction']['directory']}"
            )
    except (DownloadError, OSError) as error:
        print(f"数据准备失败：{error}", file=sys.stderr)
        print("上一次完整成功文件不会被自动删除或覆盖。", file=sys.stderr)
        print("未完成的.part文件会保留，重新运行时将尝试断点续传。", file=sys.stderr)
        return 1

    print("下一步：python scripts/inspect_candidates.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
