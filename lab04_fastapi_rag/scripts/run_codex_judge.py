from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.formal_judge import run_formal_judge  # noqa: E402
from src.run_state import resolve_run_dir  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="串行运行冻结的Codex独立盲审。"
    )
    parser.add_argument("--experiment-run-id", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print("[检查点4/步骤4] 串行运行Codex Judge")
    try:
        run_dir = resolve_run_dir(args.experiment_run_id)
        summary = run_formal_judge(
            run_dir,
            progress=lambda pos, total, qid, state: print(
                f"[{pos:02d}/{total:02d}] {qid}: {state}",
                flush=True,
            ),
        )
    except (
        FileExistsError,
        FileNotFoundError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as error:
        print(
            f"Codex Judge失败：{type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return 1
    print(f"状态：{summary['status']}")
    print(f"完成：{summary['completed_count']}/{summary['input_count']}")
    print(f"Judge状态：{summary['status_counts']}")
    print(f"回答等级：{summary['grade_counts']}")
    print(
        "下一步：python scripts/build_evaluation_report.py "
        f"--experiment-run-id {run_dir.name}"
    )
    return 0 if summary["remaining_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
