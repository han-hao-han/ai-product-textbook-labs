"""Run the network-free Q01-Q10 audit for combined Prompt v12."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from src.internal_call_arithmetic_guard_v2_3_4_2_validation import run_offline_validation
from src.online_native_tool_candidate_combined_v12 import NativeToolOnlineCandidateCombinedV12


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    output_dir = args.output_dir or (
        PROJECT_ROOT / "results" / "raw" /
        datetime.now().astimezone().strftime(
            "combined_prompt_v12_offline_%Y%m%dT%H%M%S_%f%z"
        )
    )
    summary = run_offline_validation(
        output_dir,
        candidate_type=NativeToolOnlineCandidateCombinedV12,
        audit_schema_version="1.5.6-h3-combined-prompt-v12-offline-summary-v1",
        case_schema_version="1.5.6-h3-combined-prompt-v12-offline-case-v1",
        session_prefix="combined-prompt-v12-audit",
        result_root="results/raw/combined_prompt_v12_offline_validation",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
