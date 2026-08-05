"""Build local deterministic answers for the candidate H2 questions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.data_audit import (  # noqa: E402
    DataAuditError,
    read_online_retail_workbook,
    save_audit_report,
)
from src.h2_reference_answers import (  # noqa: E402
    build_h2_reference_answers,
)
from src.retail_cleaning import build_retail_data_layers  # noqa: E402


DEFAULT_WORKBOOK = PROJECT_ROOT / "data" / "raw" / "Online Retail.xlsx"
DEFAULT_OUTPUT = (
    PROJECT_ROOT / "data" / "raw" / "h2_reference_answers.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="按冻结口径生成H2固定问题的确定性参考答案。"
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        frame, _ = read_online_retail_workbook(args.input.resolve())
        layers = build_retail_data_layers(frame)
        answers = build_h2_reference_answers(layers)
        save_audit_report(answers, args.output.resolve())
    except (DataAuditError, ValueError) as exc:
        print(f"生成参考答案失败：{exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"文件写入失败：{exc}", file=sys.stderr)
        return 1

    print(
        json.dumps(
            answers["answers"],
            ensure_ascii=False,
            indent=2,
        )
    )
    print(f"\n本地参考答案：{args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
