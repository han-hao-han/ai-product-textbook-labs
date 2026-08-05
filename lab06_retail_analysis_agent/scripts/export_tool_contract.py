"""Export the frozen H3 tool whitelist from the Pydantic source of truth."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.tool_registry import TOOL_DESCRIPTIONS  # noqa: E402
from src.tool_schemas import TOOL_ARGUMENT_MODELS  # noqa: E402


DEFAULT_OUTPUT = PROJECT_ROOT / "config" / "h3_tool_contract.json"


def build_contract() -> dict[str, object]:
    tools = []
    for name, argument_model in TOOL_ARGUMENT_MODELS.items():
        tools.append(
            {
                "name": name,
                "description": TOOL_DESCRIPTIONS[name],
                "strict": True,
                "parameters": argument_model.model_json_schema(),
            }
        )
    return {
        "schema_version": "1.5.6-h3-tool-contract-v1",
        "status": "frozen_by_user_request",
        "frozen_on": "2026-07-31",
        "h2_dependencies": {
            "metric_contract": "config/h2_metric_contract.json",
            "validation_questions": "config/h2_validation_questions.json",
            "cleaning_and_metrics_must_remain_frozen": True,
        },
        "execution_policy": {
            "whitelist_only": True,
            "program_side_pydantic_validation": True,
            "additional_properties_allowed": False,
            "maximum_tool_calls_per_turn": 4,
            "maximum_tool_calls_per_model_response": 1,
            "customer_id_values_may_be_returned": False,
            "arbitrary_python_sql_shell_or_expression_allowed": False,
        },
        "tools": tools,
        "change_control": (
            "修改工具名称、职责、参数字段或参数约束前，必须重新提交用户确认。"
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="从Pydantic模型导出冻结的7工具契约。"
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(build_contract(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"已导出7个冻结工具Schema：{output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
