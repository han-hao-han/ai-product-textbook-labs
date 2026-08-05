"""Replay Q02/Q04/Q05 V3 failures against V3.1 offline cases."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.claim_controller_v3_1_saved_response_regression import (  # noqa: E402
    validate_v3_1_saved_response_regression,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    for question_id in ("q02", "q04", "q05"):
        parser.add_argument(f"--old-{question_id}", required=True, type=Path)
        parser.add_argument(f"--new-{question_id}", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = validate_v3_1_saved_response_regression(
        old_cases={"Q02": args.old_q02, "Q04": args.old_q04, "Q05": args.old_q05},
        v3_1_cases={"Q02": args.new_q02, "Q04": args.new_q04, "Q05": args.new_q05},
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
