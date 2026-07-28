from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.candidate_selector import build_candidate_pool  # noqa: E402
from src.paths import split_paths  # noqa: E402
from src.privacy_screening import screen_document_privacy  # noqa: E402
from src.xfund_loader import DataFormatError, load_xfund_documents  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="本地审计XFUND候选的隐私信号，不输出命中的原始文字"
    )
    parser.add_argument(
        "--count",
        type=int,
        default=30,
        help="显示低风险候选数量，默认30",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.count < 1:
        print("--count必须大于0", file=sys.stderr)
        return 2

    annotation_path, images_dir = split_paths("train")
    try:
        documents = load_xfund_documents(annotation_path)
        pool = build_candidate_pool(documents, images_dir)
    except (FileNotFoundError, DataFormatError, OSError) as error:
        print(f"隐私审计失败：{error}", file=sys.stderr)
        return 1

    all_screens = [screen_document_privacy(document) for document in documents]
    hard_excluded_count = sum(
        screen["hard_excluded"] for screen in all_screens
    )
    tier_counts = Counter(screen["risk_tier"] for screen in all_screens)
    ranked = sorted(
        pool,
        key=lambda item: (
            item["privacy_screen"]["risk_score"],
            len(item["privacy_screen"]["signal_categories"]),
            item["sample_id"],
        ),
    )

    print("[阶段2/H2重选] XFUND本地隐私候选审计")
    print("身份证号数值模式：硬性排除")
    print("输出限制：不打印命中的姓名、号码、地址或其他原始文字")
    print(f"总文档数：{len(documents)}")
    print(f"身份证号硬排除：{hard_excluded_count}")
    print(
        "风险层级计数："
        + "｜".join(
            f"{tier}={tier_counts.get(tier, 0)}"
            for tier in ("none_detected", "low", "medium", "high")
        )
    )
    print(f"满足图像与参考字段条件且未被硬排除：{len(pool)}")
    print("===== 未硬排除候选（信号分数仅供记录，不参与H2选样） =====")
    for index, candidate in enumerate(ranked[: args.count], start=1):
        privacy = candidate["privacy_screen"]
        categories = "、".join(privacy["signal_categories"]) or "未检出"
        features = candidate["features"]
        print(
            f"{index:02d}. {candidate['sample_id']}｜"
            f"风险分{privacy['risk_score']}｜{categories}｜"
            f"参考字段{features['reference_field_count']}｜"
            f"布局复杂度{features['layout_complexity']}"
        )
    print("说明：标注文本未检出不等于原图无隐私，最终必须人工查看。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
