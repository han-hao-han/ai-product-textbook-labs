from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_DIR / "data"
RAW_DIR = DATA_DIR / "raw"

SOURCE_REPOSITORY = "Meituan-Dianping/asap"
SOURCE_COMMIT = "975122a60065240124df62cb4d5dbfd19ed9ef2c"
DOWNLOAD_DATE = "2026-07-17"

SOURCE_FILES = {
    "train": {
        "filename": "train.csv",
        "expected_rows": 36_850,
        "expected_sha256": (
            "30912f5e2a866a4c0f654ec3461215f"
            "008b8b90d208f2c410f03369f43655de9"
        ),
    },
    "dev": {
        "filename": "dev.csv",
        "expected_rows": 4_940,
        "expected_sha256": (
            "54efc8f6bc26d63a9f87e3418cd68e47"
            "f2eb13a19085e85abe63f3eafafe2b44"
        ),
    },
    "test": {
        "filename": "test.csv",
        "expected_rows": 4_940,
        "expected_sha256": (
            "217dd27c1d5699067952474e40824935d"
            "56ecf8b5047950d6da3d1222976a2bd"
        ),
    },
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

MAIN_EXAMPLE_ID = "7688"

DEMO_IDS = [
    "7688",
    "13222",
    "2828",
    "39662",
    "24593",
]

SELECTION_SEED = "asap-lab01-fixed-subsets-v1"

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

OUTPUT_COLUMNS = [
    "review_id",
    "review_text",
    "source_star",
    "source_split",
    "location_sentiment",
    "service_sentiment",
    "price_sentiment",
    "environment_sentiment",
    "food_sentiment",
    "aspect_summary",
    "selection_role",
]


def calculate_sha256(file_path: Path) -> str:
    """计算文件 SHA-256。"""
    digest = hashlib.sha256()

    with file_path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def deterministic_key(review_id: str) -> str:
    """根据固定种子和记录 ID 生成稳定排序键。"""
    source = f"{SELECTION_SEED}:{review_id}"

    return hashlib.sha256(
        source.encode("utf-8")
    ).hexdigest()


def get_aspect_sentiment(
    row: pd.Series,
    columns: list[str],
) -> str | None:
    """把同一粗粒度维度下的细粒度标签合并。"""
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


def load_dataset() -> tuple[pd.DataFrame, dict[str, Any]]:
    """读取、校验并合并三个原始文件。"""
    frames: list[pd.DataFrame] = []
    source_manifest: dict[str, Any] = {}

    for split_name, config in SOURCE_FILES.items():
        file_path = RAW_DIR / config["filename"]

        if not file_path.exists():
            raise FileNotFoundError(
                f"缺少原始数据文件：{file_path}"
            )

        actual_hash = calculate_sha256(file_path)

        if actual_hash != config["expected_sha256"]:
            raise ValueError(
                f"{file_path.name} 的 SHA-256 不一致。\n"
                f"预期：{config['expected_sha256']}\n"
                f"实际：{actual_hash}"
            )

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
                f"{file_path.name} 的字段不符合预期："
                f"{df.columns.tolist()}"
            )

        if len(df) != config["expected_rows"]:
            raise ValueError(
                f"{file_path.name} 行数不符合预期："
                f"{len(df)}"
            )

        df = df.rename(columns=COLUMN_MAPPING)
        df["source_split"] = split_name

        frames.append(df)

        source_manifest[split_name] = {
            "filename": config["filename"],
            "row_count": len(df),
            "file_size_bytes": file_path.stat().st_size,
            "sha256": actual_hash,
        }

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

    if combined["review_id"].duplicated().any():
        raise ValueError("数据集中存在重复 review_id。")

    return combined, source_manifest


def add_derived_fields(df: pd.DataFrame) -> pd.DataFrame:
    """增加稳定筛选和人工验证所需字段。"""
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

    result["privacy_risk"] = (
        result["review_text"]
        .str.contains(
            PRIVACY_PATTERN,
            na=False,
        )
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

    result["selection_key"] = (
        result["review_id"].map(deterministic_key)
    )

    return result


def select_rows_by_ids(
    df: pd.DataFrame,
    review_ids: list[str],
) -> pd.DataFrame:
    """按照指定 ID 顺序取出记录。"""
    indexed = df.set_index(
        "review_id",
        drop=False,
    )

    missing_ids = [
        review_id
        for review_id in review_ids
        if review_id not in indexed.index
    ]

    if missing_ids:
        raise ValueError(
            f"以下固定 ID 不存在：{missing_ids}"
        )

    selected = indexed.loc[review_ids].copy()
    selected.reset_index(
        drop=True,
        inplace=True,
    )

    return selected


def build_demo_set(df: pd.DataFrame) -> pd.DataFrame:
    """生成经过人工确认的 5 条演示集。"""
    demo = select_rows_by_ids(df, DEMO_IDS)

    demo["selection_role"] = [
        "main_example",
        "positive_demo",
        "negative_demo",
        "mixed_demo",
        "environment_demo",
    ]

    return demo


def build_regression_set(
    df: pd.DataFrame,
    demo: pd.DataFrame,
) -> pd.DataFrame:
    """在演示集基础上补充 15 条回归样本。"""
    selected_frames = [demo.copy()]
    selected_ids = set(demo["review_id"].tolist())

    eligible = (
        df["review_length"].between(60, 320)
        & ~df["privacy_risk"]
    )

    group_rules = [
        (
            "regression_positive",
            (
                eligible
                & df["positive_label_count"].ge(2)
                & df["negative_label_count"].eq(0)
            ),
        ),
        (
            "regression_negative",
            (
                eligible
                & df["negative_label_count"].ge(2)
                & df["positive_label_count"].eq(0)
            ),
        ),
        (
            "regression_mixed",
            (
                eligible
                & df["positive_label_count"].ge(1)
                & df["negative_label_count"].ge(1)
            ),
        ),
        (
            "regression_service_environment",
            (
                eligible
                & (
                    df["service_sentiment"].isin(
                        ["negative", "mixed"]
                    )
                    | df["environment_sentiment"].isin(
                        ["negative", "mixed"]
                    )
                )
            ),
        ),
        (
            "regression_price_location",
            (
                eligible
                & (
                    df["price_sentiment"].notna()
                    | df["location_sentiment"].notna()
                )
            ),
        ),
    ]

    for role, mask in group_rules:
        candidates = df.loc[
            mask
            & ~df["review_id"].isin(selected_ids)
        ].copy()

        candidates = candidates.sort_values(
            by=["selection_key", "review_id"],
            kind="stable",
        )

        selected = candidates.head(3).copy()

        if len(selected) != 3:
            raise RuntimeError(
                f"{role} 可用候选不足 3 条。"
            )

        selected["selection_role"] = role
        selected_frames.append(selected)

        selected_ids.update(
            selected["review_id"].tolist()
        )

    regression = pd.concat(
        selected_frames,
        ignore_index=True,
    )

    if len(regression) != 20:
        raise RuntimeError(
            f"回归集应为 20 条，实际为 {len(regression)} 条。"
        )

    return regression


def build_extension_set(
    df: pd.DataFrame,
    regression: pd.DataFrame,
) -> pd.DataFrame:
    """按每个星级 20 条补齐到 100 条。"""
    selected_frames = [regression.copy()]
    selected_ids = set(
        regression["review_id"].tolist()
    )

    eligible = (
        df["review_length"].between(60, 320)
        & ~df["privacy_risk"]
    )

    for star in range(1, 6):
        existing_count = int(
            regression["source_star"].eq(float(star)).sum()
        )

        needed_count = 20 - existing_count

        if needed_count < 0:
            raise RuntimeError(
                f"{star} 星回归样本超过 20 条。"
            )

        if needed_count == 0:
            continue

        candidates = df.loc[
            eligible
            & df["source_star"].eq(float(star))
            & ~df["review_id"].isin(selected_ids)
        ].copy()

        candidates = candidates.sort_values(
            by=["selection_key", "review_id"],
            kind="stable",
        )

        selected = candidates.head(
            needed_count
        ).copy()

        if len(selected) != needed_count:
            raise RuntimeError(
                f"{star} 星样本不足，需要 {needed_count} 条，"
                f"实际只有 {len(selected)} 条。"
            )

        selected["selection_role"] = (
            f"extension_star_{star}"
        )

        selected_frames.append(selected)
        selected_ids.update(
            selected["review_id"].tolist()
        )

    extension = pd.concat(
        selected_frames,
        ignore_index=True,
    )

    if len(extension) != 100:
        raise RuntimeError(
            f"扩展集应为 100 条，实际为 {len(extension)} 条。"
        )

    star_counts = (
        extension["source_star"]
        .value_counts()
        .sort_index()
        .to_dict()
    )

    expected_counts = {
        1.0: 20,
        2.0: 20,
        3.0: 20,
        4.0: 20,
        5.0: 20,
    }

    if star_counts != expected_counts:
        raise RuntimeError(
            f"扩展集星级分布异常：{star_counts}"
        )

    return extension


def save_subset(
    df: pd.DataFrame,
    filename: str,
) -> dict[str, Any]:
    """保存一个固定子集并返回文件信息。"""
    output_path = DATA_DIR / filename

    output_df = df[OUTPUT_COLUMNS].copy()

    output_df.to_csv(
        output_path,
        index=False,
        encoding="utf-8-sig",
    )

    return {
        "filename": filename,
        "row_count": len(output_df),
        "sha256": calculate_sha256(output_path),
        "review_ids": output_df["review_id"].tolist(),
    }


def main() -> None:
    dataset, source_manifest = load_dataset()
    dataset = add_derived_fields(dataset)

    demo = build_demo_set(dataset)

    main_example = demo.loc[
        demo["review_id"].eq(MAIN_EXAMPLE_ID)
    ].copy()

    regression = build_regression_set(
        dataset,
        demo,
    )

    extension = build_extension_set(
        dataset,
        regression,
    )

    subsets = {
        "main": save_subset(
            main_example,
            "feedback_main_1.csv",
        ),
        "demo": save_subset(
            demo,
            "feedback_demo_5.csv",
        ),
        "regression": save_subset(
            regression,
            "feedback_regression_20.csv",
        ),
        "extension": save_subset(
            extension,
            "feedback_extension_100.csv",
        ),
    }

    manifest = {
        "dataset_name": "ASAP",
        "dataset_description": (
            "A Chinese restaurant review dataset for "
            "aspect-category sentiment analysis and rating prediction."
        ),
        "source_repository": SOURCE_REPOSITORY,
        "source_commit": SOURCE_COMMIT,
        "license": "Apache-2.0",
        "download_date": DOWNLOAD_DATE,
        "original_files_redistributed": False,
        "source_files": source_manifest,
        "source_column_mapping": COLUMN_MAPPING,
        "selection_seed": SELECTION_SEED,
        "main_example_id": MAIN_EXAMPLE_ID,
        "manually_confirmed_demo_ids": DEMO_IDS,
        "subset_relationship": (
            "main_1 is contained in demo_5; "
            "demo_5 is contained in regression_20; "
            "regression_20 is contained in extension_100."
        ),
        "selection_rules": {
            "eligibility": (
                "Review length is between 60 and 320 Chinese "
                "characters and the automatic privacy pattern "
                "does not match."
            ),
            "demo_5": (
                "Five records manually reviewed and confirmed."
            ),
            "regression_20": (
                "demo_5 plus three deterministic records from "
                "each of five predefined coverage groups."
            ),
            "extension_100": (
                "regression_20 plus deterministic records until "
                "each source star rating from 1 to 5 contains "
                "exactly 20 records."
            ),
        },
        "derived_label_note": (
            "The five coarse aspect sentiment fields are "
            "deterministically derived from the official 18 "
            "fine-grained ASAP labels. They are reference labels, "
            "not outputs produced by the language model."
        ),
        "subsets": subsets,
    }

    manifest_path = DATA_DIR / "dataset_manifest.json"

    manifest_path.write_text(
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("=== 固定子集生成结果 ===")

    for subset_name, info in subsets.items():
        print(
            f"{subset_name}: "
            f"{info['row_count']} 条"
        )
        print(f"文件：{info['filename']}")
        print(f"SHA-256：{info['sha256']}")
        print()

    star_counts = (
        extension["source_star"]
        .value_counts()
        .sort_index()
    )

    print("扩展集星级分布：")

    for star, count in star_counts.items():
        print(f"{int(star)} 星：{count}")

    print()
    print(f"清单文件：{manifest_path}")
    print("FIXED_SUBSETS_OK")


if __name__ == "__main__":
    main()