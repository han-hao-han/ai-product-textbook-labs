from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.judge_inputs import prepare_judge_inputs  # noqa: E402
from src.run_state import resolve_run_dir  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="从正式attempt_001生成最小盲审输入。"
    )
    parser.add_argument("--experiment-run-id", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print("[检查点4/步骤3] 准备Codex Judge盲审输入")
    try:
        run_dir = resolve_run_dir(args.experiment_run_id)
        result = prepare_judge_inputs(run_dir)
    except (
        FileNotFoundError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as error:
        print(
            f"盲审输入准备失败：{type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return 1
    print(f"状态：{result['status']}")
    print(f"有效回答：{result['input_count']}")
    print(f"排除：{result['excluded_count']}")
    print("生成模型、分类、分数、阈值和未引用Top 5已隐藏。")
    print(
        "下一步：python scripts/run_codex_judge.py "
        f"--experiment-run-id {run_dir.name}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
