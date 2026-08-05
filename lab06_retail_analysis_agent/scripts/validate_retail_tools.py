"""Validate deterministic H3 tool outputs against frozen H2 answers."""

from __future__ import annotations

import argparse
import calendar
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.data_audit import (  # noqa: E402
    DataAuditError,
    read_online_retail_workbook,
    save_audit_report,
)
from src.retail_cleaning import build_retail_data_layers  # noqa: E402
from src.retail_tools import RetailToolService  # noqa: E402
from src.tool_registry import RetailToolRegistry  # noqa: E402


DEFAULT_WORKBOOK = PROJECT_ROOT / "data" / "raw" / "Online Retail.xlsx"
DEFAULT_REFERENCE = (
    PROJECT_ROOT / "data" / "raw" / "h2_reference_answers.json"
)
DEFAULT_RESULTS_ROOT = PROJECT_ROOT / "results" / "raw"


def _all_data() -> dict[str, Any]:
    return {
        "period": "all_data",
        "start_date": None,
        "end_date": None,
    }


def run_validation(
    registry: RetailToolRegistry,
    reference_answers: dict[str, Any],
) -> dict[str, Any]:
    actual: dict[str, Any] = {}

    actual["Q01"] = registry.execute(
        "get_sales_overview",
        {
            **_all_data(),
            "include_incomplete_period_warning": True,
        },
    )["data"]
    actual["Q02"] = registry.execute(
        "rank_products",
        {
            **_all_data(),
            "metric": "sales_amount",
            "top_n": 5,
        },
    )["data"]
    actual["Q03"] = registry.execute(
        "analyze_regions",
        {
            **_all_data(),
            "metric": "sales_amount",
            "top_n": 5,
            "excluded_country": "United Kingdom",
        },
    )["data"]
    q04_tool = registry.execute(
        "analyze_time_trend",
        {
            **_all_data(),
            "grain": "month",
            "metric": "sales_amount",
            "exclude_incomplete_periods": True,
        },
    )["data"]
    actual["Q04"] = {
        "metric": q04_tool["metric"],
        "excluded_incomplete_period": (
            q04_tool["excluded_incomplete_periods"][0]
        ),
        "peak_complete_month": q04_tool["peak_period"],
        "peak_month_metrics": q04_tool["peak_period_metrics"],
    }
    actual["Q05"] = registry.execute(
        "compare_segments",
        {
            **_all_data(),
            "comparison": "united_kingdom_vs_other",
        },
    )["data"]
    peak_year, peak_month = (
        int(part) for part in q04_tool["peak_period"].split("-")
    )
    peak_month_end = calendar.monthrange(peak_year, peak_month)[1]
    q06_products = registry.execute(
        "rank_products",
        {
            "period": "custom",
            "start_date": f"{q04_tool['peak_period']}-01",
            "end_date": (
                f"{q04_tool['peak_period']}-{peak_month_end:02d}"
            ),
            "metric": "sales_amount",
            "top_n": 3,
        },
    )["data"]["ranking"]
    actual["Q06"] = {
        "peak_complete_month": q04_tool["peak_period"],
        "peak_month_metrics": q04_tool["peak_period_metrics"],
        "top_3_products_in_peak_month": q06_products,
    }
    customer = registry.execute(
        "analyze_customers",
        {
            **_all_data(),
            "include_coverage": True,
        },
    )["data"]
    privacy_note = customer.pop("privacy_note")
    actual["Q07"] = {
        "overall": {
            key: actual["Q01"][key]
            for key in (
                "sales_amount_gbp",
                "sales_quantity_items",
                "order_count",
                "average_order_value_gbp",
            )
        },
        "known_customer_subset": customer,
        "privacy_note": privacy_note,
    }

    cases = []
    for question_id in [f"Q{number:02d}" for number in range(1, 8)]:
        expected = reference_answers[question_id]
        observed = actual[question_id]
        cases.append(
            {
                "question_id": question_id,
                "status": "passed" if observed == expected else "failed",
                "expected": expected,
                "observed": observed,
            }
        )
    return {
        "schema_version": "1.5.6-h3-tool-validation-v1",
        "created_at": datetime.now().astimezone().isoformat(),
        "scope": {
            "validated_questions": [f"Q{number:02d}" for number in range(1, 8)],
            "not_validated_here": {
                "Q08": "澄清行为属于后续Agent编排层。",
                "Q09": "利润拒答属于后续Agent边界层。",
                "Q10": "预测拒答属于后续Agent边界层。",
            },
        },
        "summary": {
            "case_count": len(cases),
            "passed": sum(case["status"] == "passed" for case in cases),
            "failed": sum(case["status"] == "failed" for case in cases),
            "all_passed": all(
                case["status"] == "passed" for case in cases
            ),
        },
        "privacy": {
            "customer_id_values_exported": False,
            "raw_rows_exported": False,
        },
        "cases": cases,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="用H2固定答案核验7个白名单工具的真实计算结果。"
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument(
        "--reference",
        type=Path,
        default=DEFAULT_REFERENCE,
    )
    parser.add_argument(
        "--results-root",
        type=Path,
        default=DEFAULT_RESULTS_ROOT,
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        frame, _ = read_online_retail_workbook(args.input.resolve())
        layers = build_retail_data_layers(frame)
        registry = RetailToolRegistry(RetailToolService(layers))
        reference = json.loads(
            args.reference.resolve().read_text(encoding="utf-8")
        )["answers"]
        report = run_validation(registry, reference)
        run_id = datetime.now().astimezone().strftime(
            "tool_validation_%Y%m%dT%H%M%S_%f%z"
        )
        output = args.results_root.resolve() / run_id / "summary.json"
        save_audit_report(report, output)
    except (DataAuditError, ValueError, KeyError, OSError) as exc:
        print(f"工具验证失败：{exc}", file=sys.stderr)
        return 1

    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"本地验证记录：{output}")
    return 0 if report["summary"]["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
