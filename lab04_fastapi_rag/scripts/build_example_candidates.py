from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.example_export import build_example_candidates  # noqa: E402
from src.run_state import resolve_run_dir  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="生成同一运行链的公开示例候选，等待人工确认。"
    )
    parser.add_argument("--experiment-run-id", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print("[H4/步骤1] 生成公开示例候选")
    try:
        run_dir = resolve_run_dir(args.experiment_run_id)
        output_dir = build_example_candidates(run_dir)
    except (
        FileExistsError,
        FileNotFoundError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as error:
        print(
            f"示例候选生成失败：{type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return 1
    print("状态：pending_human_confirmation")
    print(f"候选目录：{output_dir.relative_to(PROJECT_ROOT).as_posix()}")
    print("候选尚未导出为仓库公开示例；请先人工查看并确认。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
