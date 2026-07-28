from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.evaluation import run_formal_evaluation  # noqa: E402
from src.run_state import resolve_run_dir  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="运行冻结的30题正式RAG评价。"
    )
    parser.add_argument("--experiment-run-id", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print("[检查点4/步骤2] 运行30题正式RAG评价")
    try:
        run_dir = resolve_run_dir(args.experiment_run_id)
        summary = run_formal_evaluation(
            run_dir,
            progress=lambda pos, total, qid, state: print(
                f"[{pos:02d}/{total:02d}] {qid}: {state}",
                flush=True,
            ),
        )
    except (
        FileExistsError,
        FileNotFoundError,
        ImportError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as error:
        print(
            f"正式评价失败：{type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return 1
    print(f"状态：{summary['status']}")
    print(
        f"完成：{summary['completed_count']}/"
        f"{summary['question_count']}"
    )
    print(f"最终状态：{summary['final_states']}")
    print(
        "下一步：python scripts/prepare_judge_inputs.py "
        f"--experiment-run-id {run_dir.name}"
    )
    return 0 if summary["remaining_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
