"""Run the network-free Q01-Q10 audit with tool-routing Prompt v2."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from src.internal_call_arithmetic_guard_v2_3_4_2_validation import (
    run_offline_validation,
)
from src.online_native_tool_candidate_tool_routing_v2 import (
    NativeToolOnlineCandidateToolRoutingV2,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    output_dir = args.output_dir or (
        PROJECT_ROOT
        / "results"
        / "raw"
        / datetime.now().astimezone().strftime(
            "tool_routing_prompt_v2_offline_%Y%m%dT%H%M%S_%f%z"
        )
    )
    summary = run_offline_validation(
        output_dir,
        candidate_type=NativeToolOnlineCandidateToolRoutingV2,
        audit_schema_version=(
            "1.5.6-h3-tool-routing-prompt-v2-offline-summary-v1"
        ),
        case_schema_version=(
            "1.5.6-h3-tool-routing-prompt-v2-offline-case-v1"
        ),
        session_prefix="tool-routing-v2-audit",
        result_root="results/raw/tool_routing_prompt_v2_offline_validation",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
