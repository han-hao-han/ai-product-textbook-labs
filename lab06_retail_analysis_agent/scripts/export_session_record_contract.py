"""Export the frozen multi-turn, run-record and offline contract."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.conversation_state import (  # noqa: E402
    ConditionOperation,
    ConditionResolution,
    EffectiveConditions,
)
from src.offline_mode import (  # noqa: E402
    OFFLINE_ALLOWED,
    OFFLINE_DISABLED,
    build_mode_policy,
)
from src.run_record import (  # noqa: E402
    SessionRunRecord,
    ToolCallRecord,
    TurnRunRecord,
)
from src.safe_export import EXPORT_FILENAMES  # noqa: E402


DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "config"
    / "h3_session_record_contract.json"
)


def build_contract() -> dict[str, object]:
    return {
        "schema_version": (
            "1.5.6-h3-session-record-contract-v1"
        ),
        "status": "frozen_by_user",
        "frozen_on": "2026-07-31",
        "v2_2_2_additive_extension": {
            "status": "frozen_by_user_offline_validated",
            "added_on": "2026-08-03",
            "run_record_retains_manual_review_flags": True,
            "existing_run_record_fields_changed": False,
            "model_control_schema_changed": False,
        },
        "acceptance_harness_six_boundary_extension": {
            "status": "frozen_by_user_implemented_offline",
            "implemented_on": "2026-08-03",
            "report_validation_adds_request_and_policy_ids": True,
            "boundary_response_adds_boundary_codes": True,
            "existing_historical_records_rewritten": False,
            "h2_reference_answers_changed": False,
        },
        "multi_turn": {
            "effective_conditions_schema": (
                EffectiveConditions.model_json_schema()
            ),
            "condition_operation_schema": (
                ConditionOperation.model_json_schema()
            ),
            "condition_resolution_schema": (
                ConditionResolution.model_json_schema()
            ),
            "change_labels": [
                "inherited",
                "added",
                "modified",
                "removed",
            ],
            "cross_turn_comparison": (
                "当前轮必须重新调用工具，historical_fact_ids_used必须为空"
            ),
            "historical_reports_merged": False,
            "provider_managed_conversation": False,
        },
        "run_record": {
            "tool_call_schema": ToolCallRecord.model_json_schema(),
            "turn_schema": TurnRunRecord.model_json_schema(),
            "session_schema": SessionRunRecord.model_json_schema(),
            "maximum_tool_calls_per_turn": 4,
            "per_turn_is_independent": True,
            "failed_stage_is_retained": True,
            "raw_response_body_embedded": False,
            "raw_response_relative_path_may_be_retained": True,
        },
        "offline_mode": {
            "policy": build_mode_policy(
                api_key_configured=False
            ).model_dump(mode="json"),
            "allowed": list(OFFLINE_ALLOWED),
            "disabled": list(OFFLINE_DISABLED),
            "must_not_claim_agent_behavior": True,
        },
        "export_and_import": {
            "filenames": list(EXPORT_FILENAMES),
            "file_count": 4,
            "overwrite_existing_files": False,
            "import_is_view_only": True,
            "security_checks": [
                "禁止API Key和Authorization",
                "禁止原始CustomerID字段",
                "禁止绝对路径",
                "禁止原始数据行",
                "Pydantic Schema重新校验",
            ],
        },
        "change_control": (
            "用户冻结后，修改条件字段、变更标签、运行记录字段、"
            "离线能力或导出文件必须重新确认。"
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="导出已冻结的多轮、运行记录、离线模式和导出契约。"
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
    print(f"已导出冻结契约：{output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
