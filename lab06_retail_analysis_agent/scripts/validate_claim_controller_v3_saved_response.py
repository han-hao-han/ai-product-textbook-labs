"""Validate V3 against the saved V20 Q01 failure evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.claim_controller_v3_saved_response_regression import (  # noqa: E402
    validate_v20_q01_to_v3_regression,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--old-failure", required=True, type=Path)
    parser.add_argument("--v3-case", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = validate_v20_q01_to_v3_regression(
        old_failure_path=args.old_failure,
        v3_case_path=args.v3_case,
    )
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
