"""Run V3 offline full regression or authorized real validation."""

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

from src.claim_controller_v3_real_runner import (  # noqa: E402
    execute_validation_v3_checkpoint,
    execute_validation_v3_full,
    validate_real_request_v3_checkpoint,
    validate_real_request_v3_full,
)
from src.claim_level_report_controller_mock_v3 import ClaimLevelLogicalClientV3  # noqa: E402
from src.deepseek_internal_call_isolation_transport_mock_v2_3_4_2 import (  # noqa: E402
    CallIsolatedFrozenQuestionNativeToolMockClient,
    OfflineDeepSeekProviderV2_3_4_2,
)
from src.mock_h2_registry import FrozenH2MockRegistry  # noqa: E402
from src.retail_cleaning import build_retail_data_layers  # noqa: E402
from src.retail_tools import RetailToolService  # noqa: E402
from src.tool_registry import RetailToolRegistry  # noqa: E402
from src.tool_routing_prompt_v1_real_runner import (  # noqa: E402
    OFFLINE_CONFIRMATION,
    ToolRoutingAuthority,
)


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


def _offline_transport(_question_id: str):
    logical = ClaimLevelLogicalClientV3(
        CallIsolatedFrozenQuestionNativeToolMockClient()
    )
    return OfflineDeepSeekProviderV2_3_4_2(logical)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("offline", "real"), required=True)
    parser.add_argument("--scope", choices=("checkpoint", "full"), required=True)
    parser.add_argument("--model", default="deepseek-v4-flash")
    parser.add_argument("--response-cap", type=int)
    parser.add_argument("--automatic-retries", type=int, default=0)
    parser.add_argument("--confirm-real-model-calls")
    args = parser.parse_args()
    executor = (
        execute_validation_v3_checkpoint
        if args.scope == "checkpoint"
        else execute_validation_v3_full
    )
    if args.mode == "offline":
        authority = ToolRoutingAuthority("offline_injected_transport", "offline-not-real")
        result = executor(
            api_key="offline-v3-key",
            registry=FrozenH2MockRegistry(),
            transport_factory=_offline_transport,
            authority=authority,
            output_parent=PROJECT_ROOT / "results" / "raw",
        )
    else:
        validator = (
            validate_real_request_v3_checkpoint
            if args.scope == "checkpoint"
            else validate_real_request_v3_full
        )
        authority = validator(
            model=args.model,
            response_cap=args.response_cap,
            automatic_retries=args.automatic_retries,
            confirmation=args.confirm_real_model_calls or "",
        )
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
        result = executor(
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
