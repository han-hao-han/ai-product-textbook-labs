"""Offline preflight for the V2.1 representative real-model plan."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.real_validation_plan_v2_1 import (  # noqa: E402
    PLAN_PATH,
    validate_real_validation_plan_v2_1,
)


def main() -> int:
    preflight = validate_real_validation_plan_v2_1()
    run_id = datetime.now().astimezone().strftime(
        "v2_1_real_plan_preflight_%Y%m%dT%H%M%S_%f%z"
    )
    output_root = PROJECT_ROOT / "results" / "raw" / run_id
    summary = {
        "schema_version": "1.5.6-h3-v2.1-real-plan-preflight-v1",
        "run_id": run_id,
        "execution_mode": "offline_plan_preflight",
        "plan_path": str(PLAN_PATH.relative_to(PROJECT_ROOT)).replace(
            "\\",
            "/",
        ),
        "real_network_opened": False,
        "api_key_read": False,
        "real_model_called": False,
        "status": preflight.status,
        "question_ids": list(preflight.question_ids),
        "request_attempt_upper_bound": (
            preflight.request_attempt_upper_bound
        ),
        "expected_standard_json_requests": (
            preflight.expected_standard_json_requests
        ),
        "expected_beta_strict_tool_requests": (
            preflight.expected_beta_strict_tool_requests
        ),
        "automatic_retry_count": (
            preflight.automatic_retry_count
        ),
        "stop_on_first_case_failure": (
            preflight.stop_on_first_case_failure
        ),
        "real_model_calls_allowed": (
            preflight.real_model_calls_allowed
        ),
        "checks": list(preflight.checks),
    }
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
