from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.candidate_gallery import write_candidate_outputs  # noqa: E402
from src.candidate_selector import CandidateSelectionError, select_candidates  # noqa: E402
from src.paths import CONFIG_PATH, LOCAL_DATA_DIR, split_paths  # noqa: E402
from src.xfund_loader import DataFormatError, load_xfund_documents  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="生成5张XFUND中文教学候选及本地查看页"
    )
    parser.add_argument(
        "--split",
        choices=("train",),
        default="train",
        help="主样本和观察样本候选固定从train分组生成",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    annotation_path, images_dir = split_paths(args.split)
    print("[阶段2] 查看XFUND中文真实候选")
    print("读者学习目标：理解图片、实体标签和人工标注参考字段的对应关系。")
    print("隐私预筛：身份证号模式命中即排除；其他信号只记录，不参与候选排序。")
    print(f"标注输入：{annotation_path}")
    print(f"图片目录：{images_dir}")
    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as file:
            config = json.load(file)
        documents = load_xfund_documents(annotation_path)
        candidates = select_candidates(
            documents,
            images_dir,
            candidate_count=int(config["candidate_count"]),
        )
        manifest_path, gallery_path = write_candidate_outputs(
            candidates,
            output_dir=LOCAL_DATA_DIR,
            project_root=PROJECT_ROOT,
        )
    except (FileNotFoundError, DataFormatError, CandidateSelectionError, OSError) as error:
        print(f"候选生成失败：{error}", file=sys.stderr)
        print("请先运行：python scripts/download_xfund.py --split train", file=sys.stderr)
        return 1

    print(f"已检查文档：{len(documents)}张")
    for index, candidate in enumerate(candidates, start=1):
        privacy_categories = "、".join(
            candidate["privacy_screen"]["signal_categories"]
        ) or "未检出"
        print(
            f"候选{index}：{candidate['sample_id']}｜"
            f"{candidate['candidate_role']}｜{candidate['selection_reason']}｜"
            f"其他隐私信号记录：{privacy_categories}"
        )
    print(f"候选清单：{manifest_path}")
    print(f"本地查看页：{gallery_path}")
    print("请打开查看页，检查图片、参考字段、布局差异和潜在隐私风险。")
    print("程序不会自动确定主样本或观察样本。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
