from __future__ import annotations

import argparse
import sys
import webbrowser
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.reference_converter import convert_reference_fields  # noqa: E402
from src.subset_config import load_teaching_subset  # noqa: E402
from src.xfund_loader import (  # noqa: E402
    load_xfund_documents,
    resolve_image_path,
)
from src.paths import split_paths  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="步骤1：查看冻结XFUND中文样本及人工标注参考字段。"
    )
    parser.add_argument("--sample-id", help="默认使用教材主样本zh_train_103")
    parser.add_argument(
        "--no-open-image",
        action="store_true",
        help="只输出图片路径，不调用本地默认查看程序",
    )
    return parser.parse_args()


def _allowed_sample_ids(subset: dict) -> set[str]:
    return {subset["main"]["sample_id"]} | {
        item["sample_id"] for item in subset["observations"]
    } | {item["sample_id"] for item in subset["validation"]["samples"]}


def _unique_relation_count(document: dict) -> int:
    relations: set[tuple[str, str]] = set()
    for entity in document["document"]:
        for link in entity["linking"]:
            if isinstance(link, list) and len(link) == 2:
                relations.add(tuple(sorted((str(link[0]), str(link[1])))))
    return len(relations)


def main() -> int:
    args = parse_args()
    print("[步骤1] 查看真实XFUND中文表单")
    print("读者学习目标：理解图片、原始实体标签和人工标注参考字段的对应关系。")
    try:
        subset = load_teaching_subset(PROJECT_ROOT / "configs" / "teaching_subset.json")
        sample_id = args.sample_id or subset["main"]["sample_id"]
        if sample_id not in _allowed_sample_ids(subset):
            raise ValueError("步骤1只允许查看H2冻结且通过隐私检查的样本")
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
        reference = convert_reference_fields(document)
    except (FileNotFoundError, ValueError, OSError) as error:
        print(f"数据查看失败：{type(error).__name__}: {error}", file=sys.stderr)
        print("异常状态：请检查数据下载、冻结样本配置和图片路径。")
        return 1

    labels = Counter(str(entity["label"]).lower() for entity in document["document"])
    relation_count = _unique_relation_count(document)
    print(f"输入来源：{annotation_path}")
    print(f"样本ID：{sample_id}")
    print(f"图片：{image_path}")
    print("核心模块：XFUND读取 → 图片关联 → 显式question-answer关系转换")
    print("\n===== 原始标注摘要 =====")
    print(f"实体数：{len(document['document'])}")
    print(f"标签计数：{dict(sorted(labels.items()))}")
    print(f"原始linking对数（摘要）：{relation_count}")
    print(f"人工标注参考字段数：{len(reference['reference_fields'])}")

    print("\n===== 人工标注参考结果 =====")
    for index, field in enumerate(reference["reference_fields"], start=1):
        print(f"{index}. {field['key']} = {field['value']}")
    print("\n===== 转换警告 =====")
    if reference["conversion_warnings"]:
        for warning in reference["conversion_warnings"]:
            print(f"- {warning}")
    else:
        print("（无）")

    if args.no_open_image:
        print("图片显示：已按参数跳过，请使用上方本地路径查看。")
    else:
        opened = webbrowser.open(image_path.resolve().as_uri())
        print("图片显示：已请求使用本地默认查看程序打开。" if opened else "图片显示：自动打开失败，请使用上方路径手动查看。")
    print("生成文件：无；本步骤只读取数据。")
    print("正常状态：图片、原始标注摘要和人工标注参考字段均已显示。")
    print(f"下一步命令：python scripts/step02_extract_form.py --sample-id {sample_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
