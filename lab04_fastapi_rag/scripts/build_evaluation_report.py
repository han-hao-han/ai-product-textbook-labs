from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.checkpoint4_report import build_checkpoint4_report  # noqa: E402
from src.io_utils import read_json  # noqa: E402
from src.run_state import resolve_run_dir  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="汇总检查点4程序指标与Codex审核结果。"
    )
    parser.add_argument("--experiment-run-id", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print("[检查点4/步骤5] 构建正式评价报告")
    try:
        run_dir = resolve_run_dir(args.experiment_run_id)
        markdown_path, json_path = build_checkpoint4_report(run_dir)
        report = read_json(json_path)
    except (
        FileNotFoundError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as error:
        print(
            f"评价报告构建失败：{type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return 1
    print(f"状态：{report['status']}")
    print(f"报告：{markdown_path} 和 {json_path}")
    print("已到达检查点4，请人工查看逐题结果和Judge首次审核。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
