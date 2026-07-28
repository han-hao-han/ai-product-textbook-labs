from __future__ import annotations

import argparse
from collections import Counter
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.paths import LOCAL_DATA_DIR, split_paths  # noqa: E402
from src.reference_converter import convert_reference_fields  # noqa: E402
from src.reference_review import (  # noqa: E402
    build_final_reference,
    load_sample_review_record,
)
from src.reference_review_page import write_reference_review_page  # noqa: E402
from src.sample_service import find_document  # noqa: E402
from src.subset_config import load_teaching_subset  # noqa: E402
from src.xfund_loader import load_xfund_documents, resolve_image_path  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="生成冻结样本的本地逐字段人工标注复核页"
    )
    parser.add_argument("--sample-id", help="默认使用当前H2冻结的教材主样本")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print("[H3修订/逐字段复核] 生成本地人工标注复核页")
    print("读者学习目标：结合原图判断XFUND显式关系是否可作为最终参考结果。")
    print("本命令不调用模型，不修改XFUND原始标注，也不自动保存人工决定。")
    try:
        subset = load_teaching_subset(
            PROJECT_ROOT / "configs" / "teaching_subset.json"
        )
        allowed_ids = {subset["main"]["sample_id"]} | {
            item["sample_id"] for item in subset["observations"]
        } | {
            item["sample_id"] for item in subset["validation"]["samples"]
        }
        sample_id = args.sample_id or subset["main"]["sample_id"]
        if sample_id not in allowed_ids:
            raise ValueError("复核页只允许使用H2冻结的10张样本")

        annotation_path, images_dir = split_paths("train")
        documents = load_xfund_documents(annotation_path)
        document = find_document(documents, sample_id)
        image_path = resolve_image_path(images_dir, document)
        review_record = load_sample_review_record(
            LOCAL_DATA_DIR / "sample_reviews", sample_id
        )
        reference = convert_reference_fields(document)
        final_reference_preview = build_final_reference(
            reference["reference_fields"], review_record
        )
        output_path = write_reference_review_page(
            sample_id=sample_id,
            document=document,
            image_path=image_path,
            review_record=review_record,
            output_dir=LOCAL_DATA_DIR,
        )
    except (FileNotFoundError, ValueError, OSError) as error:
        print(
            f"复核页生成失败：{type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return 1

    duplicate_keys = Counter(
        field["key"] for field in reference["reference_fields"]
    )
    duplicate_group_count = sum(
        count > 1 for count in duplicate_keys.values()
    )
    print(f"样本ID：{sample_id}")
    print(f"数据集原始标注字段数：{len(reference['reference_fields'])}")
    print(f"同名多行候选组：{duplicate_group_count}")
    print(
        f"已记录且通过校验的校正："
        f"{len(final_reference_preview.get('recorded_correction_ids', []))}项"
    )
    preview_count = final_reference_preview.get(
        "correction_preview_field_count"
    )
    if preview_count is not None:
        print(f"应用已记录校正后的预览字段数：{preview_count}")
    print(f"当前最终参考结果状态：{review_record['final_reference_status']}")
    print(f"本地复核页：{output_path}")
    print("请打开页面逐字段核对原图，并记录确认、校正、合并或不确定项。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
