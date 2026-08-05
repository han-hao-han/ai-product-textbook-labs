"""Run the single-use combined Prompt v9 four-question checkpoint."""

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

from src.combined_prompt_v9_real_runner import (  # noqa: E402
    execute_validation_v9,
    validate_real_request_v9,
)
from src.retail_cleaning import build_retail_data_layers  # noqa: E402
from src.retail_tools import RetailToolService  # noqa: E402
from src.tool_registry import RetailToolRegistry  # noqa: E402
from src.tool_routing_prompt_v1_real_runner import ToolRoutingRealRunnerError  # noqa: E402


def _dotenv(path: Path, name: str) -> str | None:
    if not path.exists():
        return None
    pattern = re.compile(rf"^\s*{re.escape(name)}\s*=\s*(.*?)\s*$")
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if match:
            value = match.group(1).strip().strip("\"'")
            return value or None
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--response-cap", required=True, type=int)
    parser.add_argument("--automatic-retries", required=True, type=int)
    parser.add_argument("--confirm-real-model-calls", required=True)
    args = parser.parse_args()
    try:
        authority = validate_real_request_v9(
            model=args.model,
            response_cap=args.response_cap,
            automatic_retries=args.automatic_retries,
            confirmation=args.confirm_real_model_calls,
        )
    except ToolRoutingRealRunnerError as exc:
        raise SystemExit(f"authorization gate stopped execution: {exc}") from exc
    api_key = os.environ.get("LLM_API_KEY") or _dotenv(
        REPOSITORY_ROOT / ".env", "LLM_API_KEY"
    )
    workbook = PROJECT_ROOT / "data" / "raw" / "Online Retail.xlsx"
    if not api_key:
        raise SystemExit("LLM_API_KEY is missing; no real request was sent")
    if not workbook.exists():
        raise SystemExit("Online Retail workbook is missing; no real request was sent")
    registry = RetailToolRegistry(
        RetailToolService(build_retail_data_layers(pd.read_excel(workbook)))
    )
    result = execute_validation_v9(
        api_key=api_key,
        registry=registry,
        transport_factory=None,
        authority=authority,
        output_parent=PROJECT_ROOT / "results" / "raw",
    )
    print(json.dumps(result.summary, ensure_ascii=False, indent=2))
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
