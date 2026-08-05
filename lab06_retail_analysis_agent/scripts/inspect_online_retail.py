"""Inspect the frozen UCI Online Retail workbook without freezing H2 rules."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.data_audit import (  # noqa: E402
    DataAuditError,
    build_audit_report,
    masked_preview,
    read_online_retail_workbook,
    save_audit_report,
)


DEFAULT_WORKBOOK = PROJECT_ROOT / "data" / "raw" / "Online Retail.xlsx"
DEFAULT_REPORT = PROJECT_ROOT / "data" / "raw" / "audit_report.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="检查UCI Online Retail真实字段和异常信号。"
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
        default=DEFAULT_REPORT,
        help="本地JSON审计结果路径。",
    )
    parser.add_argument(
        "--show-rows",
        type=int,
        default=5,
        help="显示多少行脱敏预览，默认5。",
    )
    return parser.parse_args()


def print_summary(report: dict, preview: list[dict]) -> None:
    structure = report["structure"]
    missing = report["missing_rows_by_column"]
    dates = report["date"]
    unique = report["unique_non_missing_values"]
    quantity = report["quantity"]
    price = report["unit_price"]
    cancellations = report["cancellation_signals"]
    overlap = report["signal_overlap"]

    print("[真实数据概况]")
    print(f"工作表：{', '.join(report['file']['sheet_names'])}")
    print(f"记录数：{structure['row_count']:,}")
    print(f"字段数：{structure['column_count']}")
    print(f"字段：{', '.join(structure['columns'])}")
    print(f"重复行：{structure['duplicate_rows']:,}")
    print(f"时间范围：{dates['minimum']} 至 {dates['maximum']}")
    print(f"无法解析的日期：{dates['missing_or_unparseable_rows']:,}")
    print(
        "唯一非缺失值："
        f"订单/发票 {unique['invoices']:,}，"
        f"商品 {unique['products']:,}，"
        f"客户 {unique['customers']:,}，"
        f"国家/地区 {unique['countries']:,}"
    )

    print("\n[缺失值]")
    for column, count in missing.items():
        print(f"{column}: {count:,}")

    print("\n[数量符号]")
    print(json.dumps(quantity, ensure_ascii=False, indent=2))
    print("\n[单价符号]")
    print(json.dumps(price, ensure_ascii=False, indent=2))
    print("\n[取消前缀]")
    print(json.dumps(cancellations, ensure_ascii=False, indent=2))
    print("\n[取消前缀与数量符号交叉]")
    print(json.dumps(overlap, ensure_ascii=False, indent=2))

    print("\n[脱敏预览]")
    print(json.dumps(preview, ensure_ascii=False, indent=2, default=str))
    print(
        "\n说明：这里只展示事实统计；负数量、退货和销售额口径仍待H2确认。"
    )


def main() -> int:
    args = parse_args()
    if args.show_rows < 0:
        print("错误：--show-rows不能为负数。", file=sys.stderr)
        return 2

    try:
        frame, sheet_names = read_online_retail_workbook(args.input.resolve())
        report = build_audit_report(
            frame,
            workbook_path=args.input.resolve(),
            sheet_names=sheet_names,
        )
        preview = masked_preview(frame, args.show_rows)
        save_audit_report(report, args.output.resolve())
    except DataAuditError as exc:
        print(f"数据审计失败：{exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"文件写入失败：{exc}", file=sys.stderr)
        return 1

    print_summary(report, preview)
    print(f"\n本地审计结果：{args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
