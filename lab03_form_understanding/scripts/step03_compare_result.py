from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.comparison_pipeline import (  # noqa: E402
    ComparisonInputError,
    compare_saved_result,
)
from src.paths import LOCAL_DATA_DIR, RESULTS_DIR, split_paths  # noqa: E402
from src.subset_config import load_teaching_subset  # noqa: E402
from src.xfund_loader import load_xfund_documents  # noqa: E402


STATUS_LABELS = {
    "exact_match": "完全一致",
    "normalized_match": "规范化后一致",
    "different_value": "值不一致",
    "different_pairing": "配对不一致",
    "not_in_model_output": "模型输出中未找到",
    "not_in_dataset_annotation": "数据集原始标注中未找到",
}
DIAGNOSTIC_LABELS = {
    "reference_value_contained_in_model_value": "数据集值包含于模型值",
    "model_value_contained_in_reference_value": "模型值包含于数据集值",
    "same_value_different_key": "同值异键",
    "checkbox_symbol_difference": "复选符号差异",
    "same_key_multiple_dataset_values_combined": "同键多行可能被模型合并",
    "high_key_similarity": "字段名高度相似",
    "high_value_similarity": "字段值高度相似",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="检查点3：比较模型结果、XFUND原始标注与人工复核后的最终参考结果。"
    )
    parser.add_argument("--sample-id", help="默认使用当前H2冻结的教材主样本")
    parser.add_argument(
        "--result-file",
        type=Path,
        help="可选：比较指定历史parsed结果；默认读取results/current/<sample_id>.json",
    )
    return parser.parse_args()


def _allowed_sample_ids(subset: dict) -> set[str]:
    return {subset["main"]["sample_id"]} | {
        item["sample_id"] for item in subset["observations"]
    } | {item["sample_id"] for item in subset["validation"]["samples"]}


def _model_text(row: dict) -> str:
    if row["model_index"] is None:
        return "（未找到）"
    return f"{row['model_key']} = {row['model_value']}"


def main() -> int:
    args = parse_args()
    print("[检查点3/H3修订] 两层字段比较")
    print("读者学习目标：区分数据集原始标注一致性与人工复核后的内容正确性。")
    print("本命令只读取本地结果与复核记录，不调用模型，不修改XFUND原始标注。")
    try:
        subset = load_teaching_subset(
            PROJECT_ROOT / "configs" / "teaching_subset.json"
        )
        sample_id = args.sample_id or subset["main"]["sample_id"]
        if sample_id not in _allowed_sample_ids(subset):
            raise ComparisonInputError("比较入口只允许使用H2冻结样本")
        result_path = args.result_file or (
            RESULTS_DIR / "current" / f"{sample_id}.json"
        )

        annotation_path, _ = split_paths("train")
        documents = load_xfund_documents(annotation_path)
        document = next(
            (item for item in documents if str(item["id"]) == sample_id), None
        )
        if document is None:
            raise ComparisonInputError(
                f"XFUND训练标注中不存在样本：{sample_id}"
            )

        print(f"模型结果：{result_path}")
        print(
            f"数据集原始标注来源：{annotation_path}中的显式question-answer关系"
        )
        print(f"样本ID：{sample_id}")
        print(
            "核心模块：原始标注转换 → 严格一致性比较 → 诊断提示 → "
            "人工复核记录 → 最终参考结果比较"
        )
        outcome = compare_saved_result(
            sample_id=sample_id,
            result_path=result_path,
            document=document,
            comparisons_dir=RESULTS_DIR / "comparisons",
            project_root=PROJECT_ROOT,
            review_records_dir=LOCAL_DATA_DIR / "sample_reviews",
        )
    except (FileNotFoundError, ComparisonInputError, ValueError, OSError) as error:
        print(f"比较失败：{type(error).__name__}: {error}", file=sys.stderr)
        print(
            "异常状态：不会自动调用模型；请检查current、复核记录，"
            "或通过--result-file指定历史parsed结果。"
        )
        return 1

    payload = outcome["payload"]
    comparison = payload["dataset_annotation_comparison"]
    summary = comparison["summary"]
    print("\n===== 第一层：逐个数据集原始标注字段比较 =====")
    for row in comparison["dataset_annotation_results"]:
        label = STATUS_LABELS[row["status"]]
        hint_text = ""
        if row["diagnostic_hints"]:
            hint_text = "｜提示：" + "、".join(
                DIAGNOSTIC_LABELS[hint] for hint in row["diagnostic_hints"]
            )
        print(
            f"[{label}] 数据集：{row['dataset_key']} = "
            f"{row['dataset_value']}｜模型：{_model_text(row)}{hint_text}"
        )

    print("\n===== 模型独有字段 =====")
    if comparison["model_only_fields"]:
        for row in comparison["model_only_fields"]:
            print(
                f"[数据集原始标注中未找到] "
                f"{row['model_key']} = {row['model_value']}"
            )
    else:
        print("（无）")

    print("\n===== 第一层汇总 =====")
    print(f"数据集原始标注字段数：{summary['dataset_annotation_field_count']}")
    print(f"完全一致：{summary['exact_match']}")
    print(f"规范化后一致：{summary['normalized_match']}")
    print(f"值不一致：{summary['different_value']}")
    print(f"配对不一致：{summary['different_pairing']}")
    print(f"模型输出中未找到：{summary['not_in_model_output']}")
    print(f"数据集原始标注中未找到：{summary['not_in_dataset_annotation']}")
    consistency = summary["dataset_annotation_consistency_rate"]
    consistency_text = "不适用" if consistency is None else f"{consistency:.2%}"
    print(f"数据集原始标注一致率：{consistency_text}")
    print("说明：该指标不代表模型正确率，诊断提示也不自动判对。")

    final_reference = payload["final_reference"]
    print("\n===== 第二层：最终参考结果 =====")
    print(f"人工复核状态：{final_reference['status']}")
    evaluation_context = final_reference.get("evaluation_context")
    if (
        isinstance(evaluation_context, dict)
        and evaluation_context.get("usage")
        == "teaching_post_run_adjudication_only"
    ):
        print("评价范围：模型运行后的教学性人工裁决")
        print("正式验证统计：不纳入")
    final_comparison = payload["final_reference_comparison"]
    if final_comparison is None:
        print("参考字段识别正确率：暂不计算")
        print("原因：必须先结合原图确认或校正最终参考结果。")
    else:
        final_summary = final_comparison["summary"]
        accuracy = final_summary["reference_field_recognition_accuracy"]
        accuracy_text = "不适用" if accuracy is None else f"{accuracy:.2%}"
        print(f"最终参考字段数：{final_summary['reference_field_count']}")
        print(f"参考字段识别正确率：{accuracy_text}")
    print(f"比较结果：{outcome['output_path']}")
    print("正常状态：第一层始终保留；第二层指标受人工复核状态门禁。")
    print("下一步：打开本地逐字段复核页，结合原图确认或记录校正。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
