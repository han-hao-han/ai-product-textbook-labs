"""Run explicitly selected frozen questions with an approved model-call cap."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.agent_orchestrator import (  # noqa: E402
    AgentTurnOutcome,
    RetailAgentOrchestrator,
)
from src.conversation_state import (  # noqa: E402
    EffectiveConditions,
    resolve_conditions,
)
from src.deepseek_client import (  # noqa: E402
    DEEPSEEK_MODEL,
    DeepSeekChatClient,
    DeepSeekClientError,
)
from src.fixed_question_validation import (  # noqa: E402
    load_frozen_questions,
    validate_fixed_question,
)
from src.retail_cleaning import build_retail_data_layers  # noqa: E402
from src.retail_tools import RetailToolService  # noqa: E402
from src.run_record import (  # noqa: E402
    FailureRecord,
    SessionRunRecord,
    ToolCallRecord,
    TurnRunRecord,
    save_session_run_record,
)
from src.tool_registry import RetailToolRegistry  # noqa: E402


WORKBOOK_PATH = PROJECT_ROOT / "data" / "raw" / "Online Retail.xlsx"
REPOSITORY_ROOT = PROJECT_ROOT.parent
CONFIRMATION_TEXT = "I_UNDERSTAND_REAL_MODEL_CALLS"


class ApprovedCallClient:
    def __init__(self, client: DeepSeekChatClient, limit: int) -> None:
        self.client = client
        self.limit = limit
        self.used = 0

    def complete(self, *, messages, tools):
        if self.used >= self.limit:
            raise DeepSeekClientError(
                "已达到命令行明确批准的真实模型响应上限"
            )
        self.used += 1
        return self.client.complete(messages=messages, tools=tools)


def _timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _session_id_for_run(run_id: str) -> str:
    safe_run_id = re.sub(r"[^A-Za-z0-9_-]", "_", run_id)
    return f"SESSION-{safe_run_id}"


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


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


def _turn_record(
    outcome: AgentTurnOutcome,
    *,
    created_at: str,
    raw_path: str,
    parsed_path: str,
) -> TurnRunRecord:
    failures = []
    if outcome.status == "failed":
        allowed_stages = {
            "model_response",
            "tool_name",
            "argument_schema",
            "tool_execution",
            "fact_generation",
            "chart_generation",
            "report_validation",
        }
        stage = (
            outcome.error_stage
            if outcome.error_stage in allowed_stages
            else "model_response"
        )
        failures.append(
            FailureRecord(
                failure_id="FAIL-001",
                call_id=None,
                stage=stage,
                error_type="AgentTurnFailure",
                message=outcome.error_message or "未知Agent失败",
                raw_response_path=raw_path,
            )
        )
    return TurnRunRecord(
        schema_version="1.5.6-h3-turn-run-record-v1",
        session_id=outcome.session_id,
        turn_id=outcome.turn_id,
        created_at=created_at,
        execution_mode="online_agent",
        original_question=outcome.original_question,
        clarification_question=(
            None
            if outcome.clarification is None
            else outcome.clarification.message
        ),
        clarification_answer=None,
        condition_resolution=resolve_conditions(
            EffectiveConditions.empty(),
            [],
        ),
        tool_calls=[
            ToolCallRecord(
                call_id=call.call_id,
                analysis_target=outcome.original_question,
                reason_summary=(
                    f"模型为当前问题选择白名单工具{call.tool_name}。"
                ),
                tool_name=call.tool_name,
                arguments=call.arguments,
                model_selected=True,
                status="succeeded",
                result_path=call.result_path,
                error_stage=None,
                error_message=None,
            )
            for call in outcome.tool_calls
        ],
        facts=list(outcome.facts),
        charts=list(outcome.charts),
        report_markdown=outcome.report_markdown,
        report_validation=outcome.report_validation,
        failures=failures,
        cross_turn_comparison=False,
        historical_fact_ids_used=[],
        raw_model_response_path=raw_path,
        parsed_tool_calls_path=parsed_path,
        real_model_called=True,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--question-id",
        action="append",
        required=True,
        help="可重复，例如 --question-id Q01 --question-id Q06",
    )
    parser.add_argument(
        "--approved-model-responses",
        type=int,
        required=True,
        help="本次明确批准的真实模型响应硬上限。",
    )
    parser.add_argument(
        "--confirm-real-model-calls",
        required=True,
        help=f"必须填写：{CONFIRMATION_TEXT}",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.confirm_real_model_calls != CONFIRMATION_TEXT:
        raise SystemExit("未提供真实模型调用确认文本，已停止。")
    if args.approved_model_responses < 1:
        raise SystemExit("批准的模型响应上限必须大于零。")
    api_key = os.environ.get("LLM_API_KEY") or _load_dotenv_value(
        REPOSITORY_ROOT / ".env",
        "LLM_API_KEY",
    )
    if not api_key:
        raise SystemExit("缺少LLM_API_KEY，未发起真实调用。")
    if not WORKBOOK_PATH.exists():
        raise SystemExit("缺少本地Online Retail工作簿。")

    questions = load_frozen_questions()
    unknown = [
        question_id
        for question_id in args.question_id
        if question_id not in questions
    ]
    if unknown:
        raise SystemExit(f"未知固定问题：{','.join(unknown)}")

    frame = pd.read_excel(WORKBOOK_PATH)
    registry = RetailToolRegistry(
        RetailToolService(build_retail_data_layers(frame))
    )
    client = ApprovedCallClient(
        DeepSeekChatClient(api_key=api_key),
        args.approved_model_responses,
    )
    orchestrator = RetailAgentOrchestrator(
        client=client,
        registry=registry,
    )

    run_id = datetime.now().astimezone().strftime(
        "agent_online_%Y%m%dT%H%M%S_%f%z"
    )
    relative_root = f"results/raw/{run_id}"
    output_root = PROJECT_ROOT / relative_root
    session_id = _session_id_for_run(run_id)
    created_at = _timestamp()
    turns = []
    validations = []

    for index, question_id in enumerate(args.question_id, start=1):
        turn_id = f"TURN-{index:03d}"
        outcome = orchestrator.run_turn(
            session_id=session_id,
            turn_id=turn_id,
            question=questions[question_id]["question"],
            result_root=relative_root,
        )
        turn_root = output_root / turn_id
        raw_relative = f"{relative_root}/{turn_id}/raw_responses.json"
        parsed_relative = (
            f"{relative_root}/{turn_id}/parsed_tool_calls.json"
        )
        _write_json(
            turn_root / "raw_responses.json",
            list(outcome.raw_responses),
        )
        _write_json(
            turn_root / "parsed_tool_calls.json",
            [
                {
                    "call_id": call.call_id,
                    "provider_call_id": call.provider_call_id,
                    "tool_name": call.tool_name,
                    "arguments": call.arguments,
                }
                for call in outcome.tool_calls
            ],
        )
        for call in outcome.tool_calls:
            result_path = PROJECT_ROOT / call.result_path
            _write_json(result_path, call.result)
        validation = validate_fixed_question(question_id, outcome)
        _write_json(
            turn_root / "fixed_question_validation.json",
            validation.model_dump(mode="json"),
        )
        validations.append(validation)
        turns.append(
            _turn_record(
                outcome,
                created_at=_timestamp(),
                raw_path=raw_relative,
                parsed_path=parsed_relative,
            )
        )

    record = SessionRunRecord(
        schema_version="1.5.6-h3-session-run-record-v1",
        session_id=session_id,
        execution_mode="online_agent",
        created_at=created_at,
        updated_at=_timestamp(),
        dataset_name="UCI Online Retail",
        dataset_id=352,
        workbook_sha256=(
            "43465a06f2ccf7c8b5bd2892bc7defb52f97487934fe93b16"
            "ae4c3936424676d"
        ),
        metric_contract_version="1.5.6-h2-metric-contract-v1",
        model_provider="DeepSeek",
        model_id=DEEPSEEK_MODEL,
        real_model_called=True,
        turns=turns,
    )
    save_session_run_record(
        record,
        output_root / "session_run_record.json",
    )
    summary = {
        "run_id": run_id,
        "question_ids": args.question_id,
        "approved_model_responses": args.approved_model_responses,
        "actual_model_responses": client.used,
        "passed": sum(
            result.status == "passed" for result in validations
        ),
        "failed": sum(
            result.status == "failed" for result in validations
        ),
        "manual_review_items": [
            {
                "question_id": result.question_id,
                "items": result.manual_review_items,
            }
            for result in validations
            if result.manual_review_items
        ],
    }
    _write_json(output_root / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
