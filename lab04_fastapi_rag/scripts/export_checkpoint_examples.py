from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.example_export import export_checkpoint_examples  # noqa: E402
from src.run_state import resolve_run_dir  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="导出经人工确认的四组同一运行链检查点示例。"
    )
    parser.add_argument("--experiment-run-id", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print("[H4/步骤2] 导出公开检查点示例")
    try:
        run_dir = resolve_run_dir(args.experiment_run_id)
        output_dir = export_checkpoint_examples(run_dir)
    except (
        FileExistsError,
        FileNotFoundError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as error:
        print(
            f"公开示例导出失败：{type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return 1
    print("状态：passed")
    print(f"公开示例目录：{output_dir.relative_to(PROJECT_ROOT).as_posix()}")
    print("四组检查点来自同一实验运行；完整本地运行记录未导出。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
