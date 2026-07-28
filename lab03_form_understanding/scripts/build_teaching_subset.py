from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.paths import LOCAL_DATA_DIR, split_paths  # noqa: E402
from src.subset_config import (  # noqa: E402
    SubsetConfigError,
    load_teaching_subset,
    main_observation_ids,
)
from src.validation_gallery import write_validation_candidate_outputs  # noqa: E402
from src.validation_selector import (  # noqa: E402
    DIFFICULTY_GROUPS,
    ValidationSelectionError,
    select_validation_candidates,
)
from src.xfund_loader import DataFormatError, load_xfund_documents  # noqa: E402


CONFIG_PATH = PROJECT_ROOT / "configs" / "teaching_subset.json"


def main() -> int:
    annotation_path, images_dir = split_paths("train")
    print("[阶段2] 生成固定验证候选")
    print("读者学习目标：在模型运行前，依据数据特征固定验证集。")
    print("难度依据：字段、实体、长值、多行文本、键值距离和重复键名。")
    print("隐私预筛：身份证号模式命中即排除；其他信号只记录，不参与难度选样。")
    try:
        config = load_teaching_subset(CONFIG_PATH)
        excluded_ids = main_observation_ids(config)
        documents = load_xfund_documents(annotation_path)
        candidates = select_validation_candidates(
            documents,
            images_dir,
            excluded_ids=excluded_ids,
        )
        manifest_path, gallery_path = write_validation_candidate_outputs(
            candidates,
            output_dir=LOCAL_DATA_DIR,
            project_root=PROJECT_ROOT,
            excluded_ids=excluded_ids,
        )
    except (
        FileNotFoundError,
        SubsetConfigError,
        DataFormatError,
        ValidationSelectionError,
        OSError,
    ) as error:
        print(f"验证候选生成失败：{error}", file=sys.stderr)
        return 1

    print(f"已排除主样本和观察样本：{', '.join(sorted(excluded_ids))}")
    for group in DIFFICULTY_GROUPS:
        print(f"[{group}]")
        for item in candidates:
            if item["difficulty_group"] == group:
                privacy_categories = "、".join(
                    item["privacy_screen"]["signal_categories"]
                ) or "未检出"
                print(
                    f"  {item['difficulty_label']}{item['candidate_order_in_group']}："
                    f"{item['sample_id']}｜难度分数{item['difficulty_score']:.2f}｜"
                    f"其他隐私信号记录：{privacy_categories}"
                )
    print(f"候选清单：{manifest_path}")
    print(f"本地查看页：{gallery_path}")
    print("请每个难度选择2张；程序不会自动写入正式验证集。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
