"""Guarded runner for the V2.2.1 single-Q06 Flash validation."""

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

from scripts import run_q06_real_revalidation_v2_1_revision as core  # noqa: E402
from src.q06_v2_2_1_flash_real_revalidation_plan import (  # noqa: E402
    load_q06_v2_2_1_flash_real_plan,
    validate_q06_v2_2_1_flash_real_plan,
)
from src.retail_cleaning import build_retail_data_layers  # noqa: E402
from src.retail_tools import RetailToolService  # noqa: E402
from src.tool_registry import RetailToolRegistry  # noqa: E402


FLASH_MODEL = "deepseek-v4-flash"
CONFIRMATION = "I_AUTHORIZE_Q06_V2_2_1_FLASH_REAL_REVALIDATION"
REQUIRED_RESPONSE_FORMATS = [
    None,
    None,
    {"type": "json_object"},
]


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
) -> core.ValidatedQ06ExecutionAuthority:
    candidate = (
        load_q06_v2_2_1_flash_real_plan()
        if plan is None
        else plan
    )
    preflight = validate_q06_v2_2_1_flash_real_plan(candidate)
    if args.question_id != "Q06":
        raise ValueError("question must be exactly Q06")
    if args.approved_model_responses != 3:
        raise ValueError("approved model response limit must be exactly three")
    if args.automatic_retries != 0:
        raise ValueError("automatic retries must be zero")
    if args.confirm_real_model_calls != CONFIRMATION:
        raise ValueError("exact V2.2.1 Flash confirmation is missing")
    if preflight.guarded_runner_ready is not True:
        raise ValueError("V2.2.1 guarded runner is not offline validated")
    if preflight.real_model_calls_allowed is not True:
        raise ValueError("V2.2.1 plan has no separate real-call authority")
    return core.ValidatedQ06ExecutionAuthority(
        plan=candidate,
        question_id="Q06",
        model=FLASH_MODEL,
        response_attempt_upper_bound=3,
        automatic_retry_count=0,
    )


def execute_v2_2_1_validation(
    *,
    api_key: str,
    registry,
    transport,
    output_parent: Path,
    authority: core.ValidatedQ06ExecutionAuthority | None = None,
    run_id: str | None = None,
) -> core.Q06ExecutionResult:
    return core.execute_q06_validation(
        api_key=api_key,
        registry=registry,
        transport=transport,
        output_parent=output_parent,
        authority=authority,
        model=FLASH_MODEL,
        required_response_formats=REQUIRED_RESPONSE_FORMATS,
        reject_finish_reason_length=True,
        run_id=run_id
        or datetime.now().astimezone().strftime(
            "q06_v2_2_1_flash_real_revalidation_%Y%m%dT%H%M%S_%f%z"
        ),
    )


def main() -> int:
    args = parse_args()
    try:
        authority = validate_execution_request(args)
    except ValueError as exc:
        raise SystemExit(
            f"authorization gate stopped execution: {exc}"
        ) from exc
    api_key = core._load_api_key()
    if not api_key:
        raise SystemExit("LLM_API_KEY is missing; no real request was sent")
    if not core.WORKBOOK_PATH.exists():
        raise SystemExit(
            "Online Retail workbook is missing; no real request was sent"
        )
    frame = pd.read_excel(core.WORKBOOK_PATH)
    registry = RetailToolRegistry(
        RetailToolService(build_retail_data_layers(frame))
    )
    result = execute_v2_2_1_validation(
        api_key=api_key,
        registry=registry,
        transport=None,
        output_parent=PROJECT_ROOT / "results" / "raw",
        authority=authority,
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
