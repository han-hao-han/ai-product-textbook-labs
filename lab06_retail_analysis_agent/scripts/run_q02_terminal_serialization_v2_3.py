"""Guarded real entry for the Q02 V2.3 terminal transport checkpoint."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.q02_terminal_serialization_v2_3_runner import (  # noqa: E402
    Q02TerminalV2_3RunnerError,
    execute_q02_validation,
    validate_real_execution_request,
)
from src.retail_cleaning import build_retail_data_layers  # noqa: E402
from src.retail_tools import RetailToolService  # noqa: E402
from src.tool_registry import RetailToolRegistry  # noqa: E402


WORKBOOK_PATH = PROJECT_ROOT / "data" / "raw" / "Online Retail.xlsx"


def _load_dotenv_value(path: Path, variable: str) -> str | None:
    if not path.exists():
        return None
    pattern = re.compile(rf"^\s*{re.escape(variable)}\s*=\s*(.*?)\s*$")
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if match is None:
            continue
        value = match.group(1).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        return value or None
    return None


def _load_api_key() -> str | None:
    return os.environ.get("LLM_API_KEY") or _load_dotenv_value(
        REPOSITORY_ROOT / ".env",
        "LLM_API_KEY",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--question-id", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--approved-model-responses", type=int, required=True)
    parser.add_argument("--automatic-retries", type=int, required=True)
    parser.add_argument("--confirm-real-model-calls", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        authority = validate_real_execution_request(
            question_id=args.question_id,
            model=args.model,
            approved_model_responses=args.approved_model_responses,
            automatic_retries=args.automatic_retries,
            confirmation=args.confirm_real_model_calls,
        )
    except Q02TerminalV2_3RunnerError as exc:
        raise SystemExit(f"authorization gate stopped execution: {exc}") from exc
    api_key = _load_api_key()
    if not api_key:
        raise SystemExit("LLM_API_KEY is missing; no real request was sent")
    if not WORKBOOK_PATH.exists():
        raise SystemExit("Online Retail workbook is missing; no real request was sent")
    registry = RetailToolRegistry(
        RetailToolService(build_retail_data_layers(pd.read_excel(WORKBOOK_PATH)))
    )
    result = execute_q02_validation(
        api_key=api_key,
        registry=registry,
        transport=None,
        authority=authority,
        output_parent=PROJECT_ROOT / "results" / "raw",
    )
    print(json.dumps(result.summary, ensure_ascii=False, indent=2))
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
