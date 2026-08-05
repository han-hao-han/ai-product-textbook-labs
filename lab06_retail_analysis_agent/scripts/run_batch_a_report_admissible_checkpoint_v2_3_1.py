"""Run the single-use V2.3.1 concentrated real Flash checkpoint."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.batch_a_report_admissible_checkpoint_v2_3_1 import (  # noqa: E402
    REAL_CONFIRMATION,
    claim_checkpoint_authorization,
    finalize_checkpoint,
    validate_checkpoint_authority,
)
from src.batch_a_safe_runner_v2_3_1 import (  # noqa: E402
    execute_batch_a_v2_3_1,
)
from src.retail_cleaning import build_retail_data_layers  # noqa: E402
from src.retail_tools import RetailToolService  # noqa: E402
from src.tool_registry import RetailToolRegistry  # noqa: E402


WORKBOOK_PATH = PROJECT_ROOT / "data" / "raw" / "Online Retail.xlsx"


def _dotenv_value(path: Path, variable: str) -> str | None:
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


def _api_key() -> str | None:
    return os.environ.get("LLM_API_KEY") or _dotenv_value(
        REPOSITORY_ROOT / ".env", "LLM_API_KEY"
    )


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-real-model-calls", required=True)
    return parser.parse_args()


def main() -> int:
    args = _args()
    authority = validate_checkpoint_authority(
        confirmation=args.confirm_real_model_calls
    )
    run_id = datetime.now().astimezone().strftime(
        "batch_a_report_admissible_v2_3_1_%Y%m%dT%H%M%S_%f%z"
    )
    claim_checkpoint_authorization(run_id)
    key = _api_key()
    if not key:
        raise SystemExit(
            "LLM_API_KEY is missing; authorization was consumed and no request was sent"
        )
    if not WORKBOOK_PATH.exists():
        raise SystemExit(
            "Online Retail workbook is missing; authorization was consumed and no request was sent"
        )
    registry = RetailToolRegistry(
        RetailToolService(build_retail_data_layers(pd.read_excel(WORKBOOK_PATH)))
    )
    result = None
    summary_path = f"results/raw/{run_id}/summary.json"
    try:
        result = execute_batch_a_v2_3_1(
            api_key=key,
            registry=registry,
            transport=None,
            authority=authority,
            output_parent=PROJECT_ROOT / "results" / "raw",
            run_id=run_id,
        )
        print(json.dumps(result.summary, ensure_ascii=False, indent=2))
        return 0 if result.passed else 1
    finally:
        if result is not None:
            finalize_checkpoint(
                run_id=run_id,
                passed=result.passed,
                summary_path=summary_path,
            )


if __name__ == "__main__":
    raise SystemExit(main())
