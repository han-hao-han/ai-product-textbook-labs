from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.extraction_pipeline import run_extraction  # noqa: E402
from src.model_client import OpenAICompatibleVisionClient  # noqa: E402
from src.paths import RESULTS_DIR, split_paths  # noqa: E402
from src.result_store import safe_error_message  # noqa: E402
from src.settings import (  # noqa: E402
    load_model_candidate,
    load_model_settings,
    require_h3_frozen,
)
from src.subset_config import load_teaching_subset  # noqa: E402
from src.xfund_loader import load_xfund_documents, resolve_image_path  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="检查点2：调用固定视觉模型识别一张已冻结XFUND中文表单。"
    )
    parser.add_argument("--sample-id", help="默认使用教材主样本zh_train_103")
    return parser.parse_args()


def _allowed_sample_ids(subset: dict) -> set[str]:
    return {subset["main"]["sample_id"]} | {
        item["sample_id"] for item in subset["observations"]
    } | {item["sample_id"] for item in subset["validation"]["samples"]}


def main() -> int:
    args = parse_args()
    settings = None
    print("[检查点2] 第一次视觉结构化识别")
    print("读者学习目标：观察模型调用、原始响应、JSON解析和Schema校验彼此独立。")
    print("本命令会向H3冻结的外部模型发送1张已通过隐私检查的表单图片。")
    print("成功后会保存raw与parsed历史，并更新该样本的current结果。")
    try:
        candidate = load_model_candidate()
        require_h3_frozen(candidate)
        subset = load_teaching_subset(PROJECT_ROOT / "configs" / "teaching_subset.json")
        sample_id = args.sample_id or subset["main"]["sample_id"]
        if sample_id not in _allowed_sample_ids(subset):
            raise ValueError("正式入口只允许使用H2冻结且通过隐私检查的样本")

        annotation_path, images_dir = split_paths("train")
        documents = load_xfund_documents(annotation_path)
        document = next(
            (item for item in documents if str(item["id"]) == sample_id), None
        )
        if document is None:
            raise ValueError(f"XFUND训练标注中不存在样本：{sample_id}")
        image_path = resolve_image_path(images_dir, document)
        if not image_path.is_file():
            raise FileNotFoundError(f"找不到样本图片：{image_path}")

        settings = load_model_settings()
        print(f"输入来源：XFUND v1.0中文训练集｜样本ID：{sample_id}")
        print(f"图片文件：{image_path}")
        print(f"固定模型：{candidate['model_id']}")
        print("核心模块：图片编码 → 真实模型调用 → raw保存 → JSON解析 → Schema校验 → current更新")
        client = OpenAICompatibleVisionClient(settings)
        outcome = run_extraction(
            sample_id=sample_id,
            image_path=image_path,
            client=client,
            results_dir=RESULTS_DIR,
            update_current=True,
            secrets=(settings.api_key,),
        )
    except Exception as error:
        secrets = (settings.api_key,) if settings is not None else ()
        message = safe_error_message(error, secrets)
        print(
            f"正式识别失败：{type(error).__name__}: {message}",
            file=sys.stderr,
        )
        print("异常状态：失败记录位于results/failed；既有current不会被覆盖。")
        print("请先检查失败阶段，不要盲目重复调用。")
        return 1

    parsed = outcome["parsed"]
    print("\n===== 模型原始响应开始 =====")
    print(outcome["response_text"])
    print("===== 模型原始响应结束 =====")
    print("\nJSON解析：通过")
    print("Schema v1校验：通过")
    print(f"返回模型：{outcome['model']}｜finish_reason：{outcome['finish_reason']}")
    print(f"耗时：{outcome['elapsed_seconds']}秒｜fields：{len(parsed.fields)}｜warnings：{len(parsed.warnings)}")

    print("\n===== fields =====")
    if parsed.fields:
        for index, field in enumerate(parsed.fields, start=1):
            print(f"{index}. {field.key} = {field.value}")
    else:
        print("（空）")
    print("\n===== warnings =====")
    if parsed.warnings:
        for index, warning in enumerate(parsed.warnings, start=1):
            print(f"{index}. {warning}")
    else:
        print("（空）")

    print(f"\n原始响应记录：{outcome['raw_path']}")
    print(f"解析历史记录：{outcome['parsed_path']}")
    print(f"当前结果：{outcome['current_path']}")
    print("正常状态：模型调用、JSON解析和Schema校验成功；这不代表字段识别正确。")
    print("下一步：请先完成检查点2人工确认，再进入人工标注参考结果比较。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
