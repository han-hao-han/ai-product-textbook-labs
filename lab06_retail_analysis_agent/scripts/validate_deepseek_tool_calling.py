"""Run three explicitly confirmed DeepSeek protocol checks."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.model_protocol_validation import (  # noqa: E402
    ModelValidationError,
    build_validation_cases,
    call_validation_case,
)


DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "results" / "raw"
BASE_URL = "https://api.deepseek.com"
MODEL = "deepseek-v4-pro"
API_KEY_VARIABLE = "LLM_API_KEY"
CONFIRMATION_TEXT = "I_UNDERSTAND_REAL_MODEL_CALLS"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="执行3次需单独确认的DeepSeek原生工具调用协议验证。"
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
    )
    parser.add_argument(
        "--confirm-real-model-calls",
        required=True,
        help=f"必须填写：{CONFIRMATION_TEXT}",
    )
    return parser.parse_args()


def _load_dotenv_value(path: Path, variable: str) -> str | None:
    if not path.exists():
        return None
    pattern = re.compile(
        rf"^\s*{re.escape(variable)}\s*=\s*(.*?)\s*$"
    )
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if not match:
            continue
        value = match.group(1).strip()
        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in {"'", '"'}
        ):
            value = value[1:-1]
        return value or None
    return None


def _save_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    if args.confirm_real_model_calls != CONFIRMATION_TEXT:
        print("未提供真实模型调用确认文本，已停止。", file=sys.stderr)
        return 2
    api_key = _load_dotenv_value(
        REPOSITORY_ROOT / ".env",
        API_KEY_VARIABLE,
    )
    if api_key is None:
        print(
            f"错误：根目录.env中未配置{API_KEY_VARIABLE}。",
            file=sys.stderr,
        )
        return 2

    run_id = datetime.now().astimezone().strftime(
        "model_validation_%Y%m%dT%H%M%S_%f%z"
    )
    output_dir = args.output_root.resolve() / run_id
    summary = {
        "schema_version": "1.5.6-model-protocol-summary-v1",
        "run_id": run_id,
        "provider": "DeepSeek",
        "base_url": BASE_URL,
        "requested_model": MODEL,
        "cases": [],
        "all_passed": False,
        "api_key_saved": False,
        "authorization_header_saved": False,
    }

    for case in build_validation_cases():
        print(f"[{case['case_id']}] {case['purpose']}")
        try:
            raw_record, evaluation = call_validation_case(
                case,
                api_key=api_key,
                base_url=BASE_URL,
                model=MODEL,
            )
            _save_json(
                output_dir / f"{case['case_id']}_raw.json",
                raw_record,
            )
            _save_json(
                output_dir / f"{case['case_id']}_evaluation.json",
                evaluation,
            )
            summary["cases"].append(evaluation)
            print(
                json.dumps(
                    evaluation,
                    ensure_ascii=False,
                    indent=2,
                )
            )
        except ModelValidationError as exc:
            failure = {
                "case_id": case["case_id"],
                "passed": False,
                "error_stage": "model_protocol_validation",
                "error_type": type(exc).__name__,
                "message": str(exc),
            }
            _save_json(
                output_dir / f"{case['case_id']}_failed.json",
                failure,
            )
            summary["cases"].append(failure)
            print(json.dumps(failure, ensure_ascii=False, indent=2))

    summary["all_passed"] = (
        len(summary["cases"]) == 3
        and all(item.get("passed") for item in summary["cases"])
    )
    _save_json(output_dir / "summary.json", summary)
    print(f"\n本地验证记录：{output_dir}")
    print(f"全部通过：{summary['all_passed']}")
    return 0 if summary["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
