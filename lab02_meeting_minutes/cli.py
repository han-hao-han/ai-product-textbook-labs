from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lab02_meeting_minutes.src.config import load_settings
from lab02_meeting_minutes.src.pipeline import run_mock_pipeline, run_real_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Lab 1.5.2 internal CLI")
    parser.add_argument("--input", required=True, type=Path, help="Path to a .md or .txt meeting transcript")
    parser.add_argument("--output", required=True, type=Path, help="Path to save JSON result")
    parser.add_argument("--meeting-date", default=None, help="Optional meeting date in YYYY-MM-DD")
    parser.add_argument("--mode", choices=["auto", "single_pass", "chunked"], default="auto")
    client_group = parser.add_mutually_exclusive_group(required=True)
    client_group.add_argument("--mock", action="store_true", help="Use deterministic mock client")
    client_group.add_argument("--real", action="store_true", help="Use configured real model API")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    force_mode = None if args.mode == "auto" else args.mode
    settings = load_settings()
    runner = run_real_pipeline if args.real else run_mock_pipeline
    result = runner(input_path=args.input, output_path=args.output, settings=settings, meeting_date=args.meeting_date, force_mode=force_mode)
    issue_count = len(result.validation_issues)
    print(f"saved: {args.output}")
    print(f"mode: {result.processing_metadata.mode.value}")
    print(f"validation_issues: {issue_count}")
    return 0 if issue_count == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
