from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.model_client import OpenAICompatibleVisionClient  # noqa: E402
from src.paths import RESULTS_DIR, split_paths  # noqa: E402
from src.result_store import safe_error_message  # noqa: E402
from src.settings import (  # noqa: E402
    load_model_candidate,
    load_model_settings,
    require_h3_frozen,
)
from src.subset_config import load_teaching_subset  # noqa: E402
from src.validation_runner import run_fixed_validation  # noqa: E402
from src.xfund_loader import load_xfund_documents  # noqa: E402


DIFFICULTY_LABELS = {"simple": "简单", "medium": "中等", "complex": "较复杂"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="步骤4：按冻结顺序串行运行6张正式验证样本。"
    )
    return parser.parse_args()


def _progress(index: int, total: int, sample_id: str, status: str) -> None:
    labels = {"running": "开始", "success": "成功", "failed": "失败"}
    print(f"[{index}/{total}] {sample_id}：{labels[status]}")


def _print_dataset_metrics(metrics: dict) -> None:
    consistency = metrics["dataset_annotation_consistency_rate"]
    consistency_text = "不适用" if consistency is None else f"{consistency:.2%}"
    print(
        f"  数据集原始标注字段数："
        f"{metrics['dataset_annotation_field_count']}"
    )
    print(f"  完全一致：{metrics['exact_match']}")
    print(f"  规范化后一致：{metrics['normalized_match']}")
    print(f"  值不一致：{metrics['different_value']}")
    print(f"  配对不一致：{metrics['different_pairing']}")
    print(f"  模型输出中未找到：{metrics['not_in_model_output']}")
    print(
        f"  数据集原始标注中未找到："
        f"{metrics['not_in_dataset_annotation']}"
    )
    print(f"  数据集原始标注一致率：{consistency_text}")


def main() -> int:
    parse_args()
    settings = None
    print("[步骤4] 运行6张固定验证")
    print("读者学习目标：观察固定顺序、串行调用、失败继续和验证完整性。")
    print("本命令由用户主动触发，将现场重新调用6张固定XFUND中文表单。")
    print("历史结果不会替代本次调用，程序不并发、不自动重试。")
    try:
        candidate = load_model_candidate()
        require_h3_frozen(candidate)
        subset = load_teaching_subset(PROJECT_ROOT / "configs" / "teaching_subset.json")
        validation_samples = subset["validation"]["samples"]
        annotation_path, images_dir = split_paths("train")
        documents = load_xfund_documents(annotation_path)
        settings = load_model_settings()
        print(f"输入来源：{annotation_path}")
        print("样本ID：" + ", ".join(item["sample_id"] for item in validation_samples))
        print(f"固定模型：{candidate['model_id']}")
        print(
            "核心模块：串行识别 → JSON解析 → Schema校验 → "
            "失败记录 → 工程指标汇总 → 可选原始标注诊断"
        )
        client = OpenAICompatibleVisionClient(settings)
        outcome = run_fixed_validation(
            validation_samples=validation_samples,
            documents=documents,
            images_dir=images_dir,
            client=client,
            results_dir=RESULTS_DIR,
            project_root=PROJECT_ROOT,
            secrets=(settings.api_key,),
            progress_callback=_progress,
        )
    except Exception as error:
        secrets = (settings.api_key,) if settings is not None else ()
        print(
            f"固定验证启动失败：{type(error).__name__}: "
            f"{safe_error_message(error, secrets)}",
            file=sys.stderr,
        )
        print("异常状态：未完成正式汇总，请检查配置和数据后再决定是否重试。")
        return 1

    payload = outcome["payload"]
    print("\n===== 逐样本状态 =====")
    for sample in payload["samples"]:
        if sample["status"] == "success":
            print(
                f"{sample['validation_order']}. {sample['sample_id']}｜"
                f"{DIFFICULTY_LABELS[sample['difficulty_group']]}｜成功｜"
                f"fields={sample['field_count']}｜"
                f"warnings={sample['warning_count']}｜"
                f"耗时={sample['elapsed_seconds']}秒"
            )
        else:
            print(
                f"{sample['validation_order']}. {sample['sample_id']}｜"
                f"{DIFFICULTY_LABELS[sample['difficulty_group']]}｜失败："
                f"{sample['error_type']}：{sample['message']}"
            )

    print("\n===== 各难度汇总 =====")
    for difficulty in ("simple", "medium", "complex"):
        group = payload["difficulty_summary"][difficulty]
        print(
            f"[{DIFFICULTY_LABELS[difficulty]}] 成功{group['successful_sample_count']}｜"
            f"失败{group['failed_sample_count']}｜"
            f"fields={group['total_field_count']}｜"
            f"warnings={group['total_warning_count']}｜"
            f"平均耗时={group['mean_elapsed_seconds']}秒"
        )
        print(" 可选诊断：数据集原始标注一致性（不代表正确率）")
        _print_dataset_metrics(group["dataset_annotation_diagnostic"])

    print("\n===== 正式验证汇总 =====")
    print(f"成功样本数：{payload['successful_sample_count']}")
    print(f"失败样本数：{payload['failed_sample_count']}")
    print(f"验证是否完整：{'是' if payload['complete'] else '否'}")
    engineering = payload["engineering_summary"]
    print(f"总fields数：{engineering['total_field_count']}")
    print(f"总warnings数：{engineering['total_warning_count']}")
    print(f"总耗时：{engineering['total_elapsed_seconds']}秒")
    print(f"平均耗时：{engineering['mean_elapsed_seconds']}秒")
    print("可选诊断：数据集原始标注一致性（不代表正确率）：")
    _print_dataset_metrics(
        payload["overall_dataset_annotation_diagnostic"]
    )
    print("参考字段识别正确率：固定验证不计算")
    print(f"生成文件：{outcome['output_path']}")
    print("正常状态：6张均成功时验证完整；任何失败都会保留并标记不完整。")
    print("下一步命令：streamlit run app.py")
    return 0 if payload["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
