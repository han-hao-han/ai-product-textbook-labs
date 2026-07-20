from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_DIR / "data" / "raw"
PROCESSED_DIR = PROJECT_DIR / "data" / "processed"
REPORT_PATH = PROCESSED_DIR / "dataset_audit.json"

FILES = {
    "train": {
        "filename": "train.csv",
        "expected_rows": 36_850,
    },
    "dev": {
        "filename": "dev.csv",
        "expected_rows": 4_940,
    },
    "test": {
        "filename": "test.csv",
        "expected_rows": 4_940,
    },
}

# 官方完整数据文件中的真实字段。
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

# 将官方字段映射为本项目统一字段。
COLUMN_MAPPING = {
    "id": "review_id",
    "review": "review_text",
    "star": "source_star",
    "Location#Transportation": "location_traffic",
    "Location#Downtown": "location_distance_from_business_district",
    "Location#Easy_to_find": "location_easy_to_find",
    "Service#Queue": "service_wait_time",
    "Service#Hospitality": "service_waiters_attitude",
    "Service#Parking": "service_parking_convenience",
    "Service#Timely": "service_serving_speed",
    "Price#Level": "price_level",
    "Price#Cost_effective": "price_cost_effective",
    "Price#Discount": "price_discount",
    "Ambience#Decoration": "environment_decoration",
    "Ambience#Noise": "environment_noise",
    "Ambience#Space": "environment_space",
    "Ambience#Sanitary": "environment_cleaness",
    "Food#Portion": "dish_portion",
    "Food#Taste": "dish_taste",
    "Food#Appearance": "dish_look",
    "Food#Recommend": "dish_recommendation",
}

LABEL_COLUMNS = [
    "location_traffic",
    "location_distance_from_business_district",
    "location_easy_to_find",
    "service_wait_time",
    "service_waiters_attitude",
    "service_parking_convenience",
    "service_serving_speed",
    "price_level",
    "price_cost_effective",
    "price_discount",
    "environment_decoration",
    "environment_noise",
    "environment_space",
    "environment_cleaness",
    "dish_portion",
    "dish_taste",
    "dish_look",
    "dish_recommendation",
]

ALLOWED_LABEL_VALUES = {-2, -1, 0, 1}
ALLOWED_STAR_VALUES = {1.0, 2.0, 3.0, 4.0, 5.0}


def calculate_sha256(file_path: Path) -> str:
    """计算文件的 SHA-256。"""
    digest = hashlib.sha256()

    with file_path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """清理原始列名，并映射为项目内部字段。"""
    normalized = df.copy()

    normalized.columns = [
        str(column).replace("\ufeff", "").strip()
        for column in normalized.columns
    ]

    actual_columns = normalized.columns.tolist()

    if actual_columns != SOURCE_COLUMNS:
        missing_columns = [
            column for column in SOURCE_COLUMNS
            if column not in actual_columns
        ]
        unexpected_columns = [
            column for column in actual_columns
            if column not in SOURCE_COLUMNS
        ]

        raise ValueError(
            "CSV 字段与预期不一致。\n"
            f"缺少字段：{missing_columns}\n"
            f"额外字段：{unexpected_columns}\n"
            f"实际字段：{actual_columns}"
        )

    return normalized.rename(columns=COLUMN_MAPPING)


def find_invalid_label_values(
    df: pd.DataFrame,
) -> dict[str, list[int | float | str]]:
    """查找不属于 -2、-1、0、1 的标签值。"""
    invalid: dict[str, list[int | float | str]] = {}

    for column in LABEL_COLUMNS:
        values = df[column].dropna().unique().tolist()

        invalid_values = [
            value
            for value in values
            if value not in ALLOWED_LABEL_VALUES
        ]

        if invalid_values:
            invalid[column] = sorted(
                [
                    value.item()
                    if hasattr(value, "item")
                    else value
                    for value in invalid_values
                ],
                key=str,
            )

    return invalid


def audit_file(
    split_name: str,
    file_path: Path,
    expected_rows: int,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """审计单个数据划分文件。"""
    source_df = pd.read_csv(
        file_path,
        encoding="utf-8-sig",
    )

    source_columns = [
        str(column).replace("\ufeff", "").strip()
        for column in source_df.columns
    ]

    df = normalize_columns(source_df)

    empty_review_mask = (
        df["review_text"].isna()
        | df["review_text"]
        .fillna("")
        .astype(str)
        .str.strip()
        .eq("")
    )

    duplicate_review_mask = df["review_text"].duplicated(
        keep=False
    )
    duplicate_id_mask = df["review_id"].duplicated(
        keep=False
    )

    star_values = df["source_star"].dropna().unique().tolist()
    invalid_star_values = sorted(
        [
            float(value)
            for value in star_values
            if float(value) not in ALLOWED_STAR_VALUES
        ]
    )

    result = {
        "split": split_name,
        "filename": file_path.name,
        "file_size_bytes": file_path.stat().st_size,
        "sha256": calculate_sha256(file_path),
        "expected_rows": expected_rows,
        "actual_rows": len(df),
        "row_count_matches": len(df) == expected_rows,
        "expected_column_count": len(SOURCE_COLUMNS),
        "actual_column_count": len(source_columns),
        "columns_match": source_columns == SOURCE_COLUMNS,
        "source_columns": source_columns,
        "canonical_columns": df.columns.tolist(),
        "duplicate_id_rows": int(duplicate_id_mask.sum()),
        "empty_review_rows": int(empty_review_mask.sum()),
        "duplicate_review_rows": int(
            duplicate_review_mask.sum()
        ),
        "duplicate_review_groups": int(
            df.loc[
                duplicate_review_mask,
                "review_text",
            ].nunique()
        ),
        "invalid_star_values": invalid_star_values,
        "invalid_label_values": find_invalid_label_values(df),
    }

    return df, result


def main() -> None:
    """执行完整数据集审计。"""
    PROCESSED_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    audit_results: dict[str, Any] = {}
    dataframes: list[pd.DataFrame] = []

    for split_name, config in FILES.items():
        file_path = RAW_DIR / config["filename"]

        if not file_path.exists():
            raise FileNotFoundError(
                f"缺少数据文件：{file_path}"
            )

        df, result = audit_file(
            split_name=split_name,
            file_path=file_path,
            expected_rows=config["expected_rows"],
        )

        split_df = df.copy()
        split_df["source_split"] = split_name

        dataframes.append(split_df)
        audit_results[split_name] = result

    combined = pd.concat(
        dataframes,
        ignore_index=True,
    )

    global_duplicate_id_mask = combined[
        "review_id"
    ].duplicated(keep=False)

    global_duplicate_review_mask = combined[
        "review_text"
    ].duplicated(keep=False)

    report = {
        "dataset": "ASAP",
        "source_repository": "Meituan-Dianping/asap",
        "source_commit": (
            "975122a60065240124df62cb4d5dbfd19ed9ef2c"
        ),
        "expected_total_rows": 46_730,
        "actual_total_rows": len(combined),
        "total_rows_match": len(combined) == 46_730,
        "global_unique_id_count": int(
            combined["review_id"].nunique()
        ),
        "global_duplicate_id_rows": int(
            global_duplicate_id_mask.sum()
        ),
        "global_duplicate_review_rows": int(
            global_duplicate_review_mask.sum()
        ),
        "global_duplicate_review_groups": int(
            combined.loc[
                global_duplicate_review_mask,
                "review_text",
            ].nunique()
        ),
        "splits": audit_results,
    }

    REPORT_PATH.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("=== ASAP 数据审计结果 ===")
    print(f"总行数：{report['actual_total_rows']}")
    print(
        "总行数符合预期："
        f"{report['total_rows_match']}"
    )
    print(
        "全局唯一 ID 数量："
        f"{report['global_unique_id_count']}"
    )
    print(
        "全局重复 ID 行数："
        f"{report['global_duplicate_id_rows']}"
    )
    print(
        "全局重复评论行数："
        f"{report['global_duplicate_review_rows']}"
    )
    print(
        "全局重复评论组数："
        f"{report['global_duplicate_review_groups']}"
    )
    print()

    for split_name, result in audit_results.items():
        print(f"[{split_name}]")
        print(
            f"行数：{result['actual_rows']} "
            f"/ 预期 {result['expected_rows']}"
        )
        print(
            "字段完全匹配："
            f"{result['columns_match']}"
        )
        print(
            "重复 ID 行数："
            f"{result['duplicate_id_rows']}"
        )
        print(
            "空评论行数："
            f"{result['empty_review_rows']}"
        )
        print(
            "重复评论行数："
            f"{result['duplicate_review_rows']}"
        )
        print(
            "非法星级："
            f"{result['invalid_star_values']}"
        )
        print(
            "非法标签："
            f"{result['invalid_label_values']}"
        )
        print(f"SHA-256：{result['sha256']}")
        print()

    print(f"审计报告：{REPORT_PATH}")
    print("ASAP_DATA_AUDIT_OK")


if __name__ == "__main__":
    main()