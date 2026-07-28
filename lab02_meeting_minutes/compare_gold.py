from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lab02_meeting_minutes.src.gold_compare import compare_gold_file


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare extraction result with main gold standard")
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = compare_gold_file(args.gold, args.result)
    payload = json.dumps(report.model_dump(), ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
        print(f"saved: {args.output}")
    print(payload)
    return 0 if report.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
