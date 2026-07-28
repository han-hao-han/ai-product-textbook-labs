from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.run_state import initialize_run  # noqa: E402
from src.source_config import load_source_config  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="初始化1.5.4独立实验运行，不下载文档或模型。"
    )
    parser.add_argument(
        "--experiment-run-id",
        help="可选；格式为fastapi_rag_YYYYMMDD_HHMMSS_<6位十六进制>",
    )
    parser.add_argument(
        "--device",
        default="auto",
        help="只在初始化时选择：auto、cpu或cuda:<index>；默认auto",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print("[初始化] 创建独立实验运行")
    print("本命令只冻结配置和设备，不下载文档、模型，也不调用在线接口。")
    try:
        config = load_source_config()
        run_dir = initialize_run(
            config=config,
            run_id=args.experiment_run_id,
            device=args.device,
        )
    except (FileExistsError, OSError, RuntimeError, ValueError) as error:
        print(f"初始化失败：{type(error).__name__}: {error}", file=sys.stderr)
        return 1

    print(f"experiment_run_id：{run_dir.name}")
    print(f"固定Release：{config.release_tag}")
    print(f"固定Commit：{config.commit}")
    print("运行目录：results/runs/<experiment_run_id>/")
    print("下一步：")
    print(
        "python scripts/download_fastapi_docs.py "
        f"--experiment-run-id {run_dir.name}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
