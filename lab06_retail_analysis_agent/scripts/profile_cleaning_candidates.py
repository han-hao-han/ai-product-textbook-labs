"""Generate H2 evidence without applying or freezing cleaning rules."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.cleaning_profile import build_cleaning_profile  # noqa: E402
from src.data_audit import (  # noqa: E402
    DataAuditError,
    read_online_retail_workbook,
    save_audit_report,
)


DEFAULT_WORKBOOK = PROJECT_ROOT / "data" / "raw" / "Online Retail.xlsx"
DEFAULT_OUTPUT = (
    PROJECT_ROOT / "data" / "raw" / "cleaning_profile.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="生成H2清洗与指标口径所需的确定性剖析证据。"
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_WORKBOOK,
        help="原始XLSX路径。",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="本地JSON证据路径。",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=20,
        help="异常类型最多展示多少个聚合组，默认20。",
    )
    return parser.parse_args()


def print_summary(profile: dict) -> None:
    print("[完全重复行保留首条后的互斥记录分类]")
    print(
        json.dumps(
            profile["record_classification_after_keep_first"],
            ensure_ascii=False,
            indent=2,
        )
    )
    print()

    print("[互斥记录分类]")
    print(
        json.dumps(
            profile["record_classification"],
            ensure_ascii=False,
            indent=2,
        )
    )

    print("\n[非C前缀负数量：主要商品/业务描述]")
    print(
        json.dumps(
            profile["negative_quantity_no_c_top_groups"],
            ensure_ascii=False,
            indent=2,
        )
    )

    print("\n[负价记录]")
    print(
        json.dumps(
            profile["negative_unit_price_groups"],
            ensure_ascii=False,
            indent=2,
        )
    )

    print("\n[缺失商品描述交叉检查]")
    print(
        json.dumps(
            profile["missing_description_cross_checks"],
            ensure_ascii=False,
            indent=2,
        )
    )

    print("\n[正常销售候选的客户覆盖]")
    print(
        json.dumps(
            profile["customer_coverage_for_normal_sales_candidate"],
            ensure_ascii=False,
            indent=2,
        )
    )

    print("\n[完全重复行敏感性]")
    print(
        json.dumps(
            profile["exact_duplicate_sensitivity"],
            ensure_ascii=False,
            indent=2,
        )
    )

    print("\n[商品描述与发票一致性]")
    print(
        json.dumps(
            {
                "product_description_consistency": profile[
                    "product_description_consistency"
                ],
                "invoice_consistency": profile["invoice_consistency"],
                "country_normalization": profile[
                    "country_normalization"
                ],
                "unit_price_precision": profile[
                    "unit_price_precision"
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    print(
        "\n说明：以上金额仅为Quantity×UnitPrice的机械诊断值，"
        "不是已冻结销售额。未执行清洗。"
    )


def main() -> int:
    args = parse_args()
    if args.top_n <= 0:
        print("错误：--top-n必须为正整数。", file=sys.stderr)
        return 2

    try:
        frame, _ = read_online_retail_workbook(args.input.resolve())
        profile = build_cleaning_profile(frame, top_n=args.top_n)
        save_audit_report(profile, args.output.resolve())
    except (DataAuditError, ValueError) as exc:
        print(f"剖析失败：{exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"文件写入失败：{exc}", file=sys.stderr)
        return 1

    print_summary(profile)
    print(f"\n本地H2证据：{args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
