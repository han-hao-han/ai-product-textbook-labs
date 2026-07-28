from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.embedding_config import load_embedding_config  # noqa: E402
from src.gate_calibration import calibrate_gate  # noqa: E402
from src.run_state import (  # noqa: E402
    require_compatible_run,
    resolve_run_dir,
)
from src.source_config import load_source_config  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="仅用冻结的50道校准题计算检索门控阈值。"
    )
    parser.add_argument("--experiment-run-id", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print("[检查点3/前置] 用冻结校准集计算检索门控阈值")
    print("正式题：仅核验文件SHA-256，不加载题目、不计算分数。")
    print("在线生成模型调用：False")
    try:
        source_config = load_source_config()
        embedding_config = load_embedding_config()
        run_dir = resolve_run_dir(args.experiment_run_id)
        run_manifest = require_compatible_run(run_dir, source_config)
        summary = calibrate_gate(
            run_dir,
            embedding_config,
            str(run_manifest["frozen_device"]),
        )
    except (
        FileExistsError,
        FileNotFoundError,
        KeyError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as error:
        print(
            f"门控阈值计算失败：{type(error).__name__}: {error}",
            file=sys.stderr,
        )
        print("未运行正式题，未调用在线生成模型。", file=sys.stderr)
        return 1

    metrics = summary["selected_metrics"]
    print(f"状态：{summary['status']}")
    print(f"正式阈值候选：{summary['selected_threshold']!r}")
    print(f"候选阈值：{summary['candidate_threshold_count']}")
    print(f"库内召回率：{metrics['in_scope_recall']:.4f}")
    print(f"负样本拒绝率：{metrics['negative_rejection_rate']:.4f}")
    print(f"平衡准确率：{metrics['balanced_accuracy']:.4f}")
    print(
        "混淆计数："
        f"TP={metrics['true_positive']}，"
        f"FN={metrics['false_negative']}，"
        f"TN={metrics['true_negative']}，"
        f"FP={metrics['false_positive']}"
    )
    print(
        "查询Embedding："
        f"{summary['query_embedding_diagnostics']['input_count']}，"
        f"最大输入Token="
        f"{summary['query_embedding_diagnostics']['max_input_tokens']}"
    )
    print("正式题Embedding/检索：False")
    print("在线生成模型调用：False")
    print("生成目录：calibration/threshold_v1/")
    print("已到达H3阈值复核点；确认前不得运行正式题或完整检查点3。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
