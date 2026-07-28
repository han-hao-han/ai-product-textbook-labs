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
from src.settings import load_model_candidate, load_model_settings  # noqa: E402
from src.subset_config import load_teaching_subset  # noqa: E402
from src.xfund_loader import (  # noqa: E402
    load_xfund_documents,
    resolve_image_path,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="H3候选视觉模型真实账号核验；不替代读者体验检查点2。"
    )
    parser.add_argument("--sample-id", help="默认使用已冻结教材主样本")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = None
    print("[阶段3/H3] 候选视觉模型真实账号核验")
    print("读者学习目标：区分官方能力说明、账号实际可调用和结果内容正确。")
    print("本命令会向配置的外部模型服务发送1张已通过隐私检查的表单图片。")
    print("本次只验证调用、JSON解析和Schema；不比较正确率，不更新current。")
    try:
        subset = load_teaching_subset(PROJECT_ROOT / "configs" / "teaching_subset.json")
        sample_id = args.sample_id or subset["main"]["sample_id"]
        allowed_ids = {subset["main"]["sample_id"]} | {
            item["sample_id"] for item in subset["observations"]
        } | {item["sample_id"] for item in subset["validation"]["samples"]}
        if sample_id not in allowed_ids:
            raise ValueError("H3核验只允许使用已冻结且通过隐私检查的样本")

        annotation_path, images_dir = split_paths("train")
        documents = load_xfund_documents(annotation_path)
        document = next(
            (item for item in documents if str(item["id"]) == sample_id), None
        )
        if document is None:
            raise ValueError(f"XFUND训练标注中不存在样本：{sample_id}")
        image_path = resolve_image_path(images_dir, document)
        settings = load_model_settings()
        candidate = load_model_candidate()

        print(f"输入来源：XFUND v1.0中文训练集｜样本ID：{sample_id}")
        print(f"候选模型：{candidate['model_id']}")
        print("核心模块：请求构造 → 真实调用 → 原始响应保存 → JSON解析 → Schema校验")
        client = OpenAICompatibleVisionClient(settings)
        outcome = run_extraction(
            sample_id=sample_id,
            image_path=image_path,
            client=client,
            results_dir=RESULTS_DIR,
            update_current=False,
            secrets=(settings.api_key,),
        )
    except Exception as error:
        secrets = (settings.api_key,) if settings is not None else ()
        message = safe_error_message(error, secrets)
        print(
            f"H3候选模型核验失败：{type(error).__name__}: {message}",
            file=sys.stderr,
        )
        print("异常状态：检查.env配置、模型权限、网络、原始响应和results/failed记录。")
        return 1

    parsed = outcome["parsed"]
    print(f"正常状态：真实调用成功，JSON解析与Schema v1校验通过。")
    print(f"识别字段数：{len(parsed.fields)}｜warnings数：{len(parsed.warnings)}")
    print(f"原始响应记录：{outcome['raw_path']}")
    print(f"解析结果记录：{outcome['parsed_path']}")
    print("下一步：人工检查上述本地结果后，再确认H3；本命令不代表字段内容正确。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
