"""Guarded real runner for the single-Q06 DeepSeek V4 Flash comparison."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import run_q06_real_revalidation_v2_1_revision as q06_runner  # noqa: E402
from src.q06_flash_comparison_plan_v2_1_revision import (  # noqa: E402
    load_q06_flash_comparison_plan,
    validate_q06_flash_comparison_plan,
)
from src.retail_cleaning import build_retail_data_layers  # noqa: E402
from src.retail_tools import RetailToolService  # noqa: E402
from src.tool_registry import RetailToolRegistry  # noqa: E402


FLASH_MODEL = "deepseek-v4-flash"
FLASH_CONFIRMATION = "I_AUTHORIZE_Q06_FLASH_COMPARISON"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--question-id", required=True)
    parser.add_argument("--approved-model-responses", type=int, required=True)
    parser.add_argument("--automatic-retries", type=int, required=True)
    parser.add_argument("--confirm-real-model-calls", required=True)
    return parser.parse_args()


def validate_execution_request(
    args: argparse.Namespace,
    *,
    plan: dict | None = None,
) -> q06_runner.ValidatedQ06ExecutionAuthority:
    candidate = load_q06_flash_comparison_plan() if plan is None else plan
    preflight = validate_q06_flash_comparison_plan(candidate)
    if args.question_id != "Q06":
        raise ValueError("question must be exactly Q06")
    if args.approved_model_responses != 3:
        raise ValueError("approved Flash response limit must be exactly three")
    if args.automatic_retries != 0:
        raise ValueError("automatic retries must be zero")
    if args.confirm_real_model_calls != FLASH_CONFIRMATION:
        raise ValueError("exact Flash comparison confirmation is missing")
    if preflight.real_model_calls_allowed is not True:
        raise ValueError("Flash comparison runner is not authorized for execution")
    return q06_runner.ValidatedQ06ExecutionAuthority(
        plan=candidate,
        question_id="Q06",
        model=FLASH_MODEL,
        response_attempt_upper_bound=3,
        automatic_retry_count=0,
    )


def main() -> int:
    args = parse_args()
    try:
        authority = validate_execution_request(args)
    except ValueError as exc:
        raise SystemExit(f"authorization gate stopped execution: {exc}") from exc
    api_key = q06_runner._load_api_key()
    if not api_key:
        raise SystemExit("LLM_API_KEY is missing; no real request was sent")
    if not q06_runner.WORKBOOK_PATH.exists():
        raise SystemExit("Online Retail workbook is missing; no real request was sent")
    frame = pd.read_excel(q06_runner.WORKBOOK_PATH)
    registry = RetailToolRegistry(
        RetailToolService(build_retail_data_layers(frame))
    )
    result = q06_runner.execute_q06_validation(
        api_key=api_key,
        registry=registry,
        transport=None,
        output_parent=PROJECT_ROOT / "results" / "raw",
        authority=authority,
        model=FLASH_MODEL,
        run_id=datetime.now().astimezone().strftime(
            "q06_flash_comparison_%Y%m%dT%H%M%S_%f%z"
        ),
    )
    print(
        json.dumps(
            {**result.summary, "output_dir": str(result.output_dir)},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
