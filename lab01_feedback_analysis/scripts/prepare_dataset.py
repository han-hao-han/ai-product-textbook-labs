from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_DIR / "data" / "raw"
PROCESSED_DIR = PROJECT_DIR / "data" / "processed"

CANDIDATE_PATH = PROCESSED_DIR / "feedback_candidates_30.csv"

SOURCE_FILES = {
    "train": "train.csv",
    "dev": "dev.csv",
    "test": "test.csv",
}

SOURCE_COLUMNS = [
    "id",
    "review",
    "star",
    "Location#Transportation",
    "Location#Downtown",
    "Location#Easy_to_find",
    "Service#Queue",
    "Service#Hospitality",
    "Service#Parking",
    "Service#Timely",
    "Price#Level",
    "Price#Cost_effective",
    "Price#Discount",
    "Ambience#Decoration",
    "Ambience#Noise",
    "Ambience#Space",
    "Ambience#Sanitary",
    "Food#Portion",
    "Food#Taste",
    "Food#Appearance",
    "Food#Recommend",
]

COLUMN_MAPPING = {
    "id": "review_id",
    "review": "review_text",
    "star": "source_star",
    "Location#Transportation": "location_traffic",
    "Location#Downtown": "location_downtown",
    "Location#Easy_to_find": "location_easy_to_find",
    "Service#Queue": "service_queue",
    "Service#Hospitality": "service_hospitality",
    "Service#Parking": "service_parking",
    "Service#Timely": "service_timely",
    "Price#Level": "price_level",
    "Price#Cost_effective": "price_cost_effective",
    "Price#Discount": "price_discount",
    "Ambience#Decoration": "environment_decoration",
    "Ambience#Noise": "environment_noise",
    "Ambience#Space": "environment_space",
    "Ambience#Sanitary": "environment_sanitary",
    "Food#Portion": "food_portion",
    "Food#Taste": "food_taste",
    "Food#Appearance": "food_appearance",
    "Food#Recommend": "food_recommend",
}

ASPECT_GROUPS = {
    "location": [
        "location_traffic",
        "location_downtown",
        "location_easy_to_find",
    ],
    "service": [
        "service_queue",
        "service_hospitality",
        "service_parking",
        "service_timely",
    ],
    "price": [
        "price_level",
        "price_cost_effective",
        "price_discount",
    ],
    "environment": [
        "environment_decoration",
        "environment_noise",
        "environment_space",
        "environment_sanitary",
    ],
    "food": [
        "food_portion",
        "food_taste",
        "food_appearance",
        "food_recommend",
    ],
}

LABEL_COLUMNS = [
    column
    for columns in ASPECT_GROUPS.values()
    for column in columns
]

# 只作为初步风险过滤，不能代替后续人工隐私检查。
PRIVACY_PATTERN = re.compile(
    r"(?:"
    r"1[3-9]\d{9}"
    r"|[\w.-]+@[\w.-]+\.[A-Za-z]{2,}"
    r"|https?://"
    r"|微信"
    r"|手机号"
    r"|QQ号"
    r")",
    flags=re.IGNORECASE,
)

SELECTION_SEED = "asap-lab01-candidates-v1"


def load_dataset() -> pd.DataFrame:
    """读取三个官方数据划分并统一字段名。"""
    frames: list[pd.DataFrame] = []

    for split_name, filename in SOURCE_FILES.items():
        file_path = RAW_DIR / filename

        if not file_path.exists():
            raise FileNotFoundError(f"缺少原始数据：{file_path}")

        df = pd.read_csv(
            file_path,
            encoding="utf-8-sig",
        )

        df.columns = [
            str(column).replace("\ufeff", "").strip()
            for column in df.columns
        ]

        if df.columns.tolist() != SOURCE_COLUMNS:
            raise ValueError(
                f"{filename} 的字段与预期不一致："
                f"{df.columns.tolist()}"
            )

        df = df.rename(columns=COLUMN_MAPPING)
        df["source_split"] = split_name
        frames.append(df)

    combined = pd.concat(
        frames,
        ignore_index=True,
    )

    combined["review_id"] = (
        combined["review_id"]
        .astype("int64")
        .astype(str)
    )

    combined["review_text"] = (
        combined["review_text"]
        .astype(str)
        .str.strip()
    )

    return combined


def get_aspect_sentiment(
    row: pd.Series,
    columns: list[str],
) -> str | None:
    """将同一粗粒度维度下的细粒度标签合并。"""
    values = {
        int(row[column])
        for column in columns
        if int(row[column]) != -2
    }

    if not values:
        return None

    if 1 in values and -1 in values:
        return "mixed"

    if -1 in values:
        return "negative"

    if 1 in values:
        return "positive"

    return "neutral"


def deterministic_key(review_id: str) -> str:
    """根据固定种子和 ID 生成稳定排序键。"""
    source = f"{SELECTION_SEED}:{review_id}"
    return hashlib.sha256(
        source.encode("utf-8")
    ).hexdigest()


def add_derived_fields(df: pd.DataFrame) -> pd.DataFrame:
    """增加人工筛选需要的统计字段。"""
    result = df.copy()

    result["review_length"] = (
        result["review_text"].str.len()
    )

    result["positive_label_count"] = (
        result[LABEL_COLUMNS].eq(1).sum(axis=1)
    )

    result["neutral_label_count"] = (
        result[LABEL_COLUMNS].eq(0).sum(axis=1)
    )

    result["negative_label_count"] = (
        result[LABEL_COLUMNS].eq(-1).sum(axis=1)
    )

    result["privacy_risk"] = result[
        "review_text"
    ].str.contains(
        PRIVACY_PATTERN,
        na=False,
    )

    for aspect, columns in ASPECT_GROUPS.items():
        result[f"{aspect}_sentiment"] = result.apply(
            lambda row: get_aspect_sentiment(
                row,
                columns,
            ),
            axis=1,
        )

    result["aspect_summary"] = result.apply(
        lambda row: "; ".join(
            f"{aspect}:{row[f'{aspect}_sentiment']}"
            for aspect in ASPECT_GROUPS
            if row[f"{aspect}_sentiment"] is not None
        ),
        axis=1,
    )

    result["selection_key"] = result[
        "review_id"
    ].map(deterministic_key)

    return result


def select_candidates(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """从不同类型中确定性选取候选评论。"""
    eligible = (
        df["review_length"].between(60, 320)
        & ~df["privacy_risk"]
    )

    group_rules = [
        (
            "positive",
            (
                eligible
                & df["source_star"].ge(4)
                & df["positive_label_count"].ge(2)
                & df["negative_label_count"].eq(0)
            ),
        ),
        (
            "negative",
            (
                eligible
                & df["source_star"].le(3)
                & df["negative_label_count"].ge(2)
                & df["positive_label_count"].eq(0)
            ),
        ),
        (
            "mixed",
            (
                eligible
                & df["positive_label_count"].ge(1)
                & df["negative_label_count"].ge(1)
            ),
        ),
        (
            "service_problem",
            (
                eligible
                & df["service_sentiment"].isin(
                    ["negative", "mixed"]
                )
            ),
        ),
        (
            "environment_problem",
            (
                eligible
                & df["environment_sentiment"].isin(
                    ["negative", "mixed"]
                )
            ),
        ),
        (
            "price_feedback",
            (
                eligible
                & df["price_sentiment"].notna()
            ),
        ),
    ]

    selected_frames: list[pd.DataFrame] = []
    selected_ids: set[str] = set()

    for group_name, mask in group_rules:
        candidates = df.loc[
            mask & ~df["review_id"].isin(selected_ids)
        ].copy()

        candidates = candidates.sort_values(
            by=["selection_key", "review_id"],
            kind="stable",
        )

        selected = candidates.head(5).copy()

        if len(selected) < 5:
            raise RuntimeError(
                f"候选组 {group_name} 不足 5 条，"
                f"实际只有 {len(selected)} 条。"
            )

        selected["candidate_group"] = group_name
        selected_frames.append(selected)

        selected_ids.update(
            selected["review_id"].tolist()
        )

    result = pd.concat(
        selected_frames,
        ignore_index=True,
    )

    output_columns = [
        "candidate_group",
        "review_id",
        "source_split",
        "source_star",
        "review_length",
        "aspect_summary",
        "positive_label_count",
        "neutral_label_count",
        "negative_label_count",
        "privacy_risk",
        "review_text",
    ]

    return result[output_columns]


def main() -> None:
    PROCESSED_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    dataset = load_dataset()
    dataset = add_derived_fields(dataset)
    candidates = select_candidates(dataset)

    candidates.to_csv(
        CANDIDATE_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    print("=== 教材候选评论生成结果 ===")
    print(f"候选总数：{len(candidates)}")
    print()

    group_counts = candidates[
        "candidate_group"
    ].value_counts(sort=False)

    for group_name, count in group_counts.items():
        print(f"{group_name}: {count}")

    print()
    print(
        "候选 ID："
        + ", ".join(candidates["review_id"].tolist())
    )
    print(f"输出文件：{CANDIDATE_PATH}")
    print("FEEDBACK_CANDIDATES_OK")


if __name__ == "__main__":
    main()