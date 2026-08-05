"""Validate the frozen V2 report boundary with a hard request cap."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.agent_orchestrator_v2 import (  # noqa: E402
    AgentTurnOutcomeV2,
    RetailAgentOrchestratorV2,
)
from src.data_audit import read_online_retail_workbook  # noqa: E402
from src.deepseek_client import (  # noqa: E402
    DEEPSEEK_MODEL,
    ChatCompletionResult,
    DeepSeekChatClient,
    DeepSeekClientError,
)
from src.fixed_question_validation import (  # noqa: E402
    load_frozen_questions,
    validate_fixed_question,
)
from src.retail_cleaning import build_retail_data_layers  # noqa: E402
from src.retail_tools import RetailToolService  # noqa: E402
from src.tool_registry import RetailToolRegistry  # noqa: E402


WORKBOOK_PATH = PROJECT_ROOT / "data" / "raw" / "Online Retail.xlsx"
QUESTION_IDS = ("Q06", "Q08", "Q09")
AUTHORIZED_RESPONSE_UPPER_BOUND = 6
CONFIRMATION_TEXT = "I_UNDERSTAND_V2_REAL_MODEL_CALLS"


class ApprovedV2Client:
    """Count attempts before transport so failures cannot bypass the cap."""

    def __init__(
        self,
        client: DeepSeekChatClient,
        limit: int,
    ) -> None:
        self.client = client
        self.limit = limit
        self.attempted = 0
        self.completed = 0

    def _reserve(self) -> None:
        if self.attempted >= self.limit:
            raise DeepSeekClientError(
                "已达到命令行明确批准的真实模型请求上限"
            )
        self.attempted += 1

    def complete_json(
        self,
        *,
        messages: list[dict[str, Any]],
    ) -> ChatCompletionResult:
        self._reserve()
        result = self.client.complete_json(messages=messages)
        self.completed += 1
        return result

    def complete_strict_tools(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> ChatCompletionResult:
        self._reserve()
        result = self.client.complete_strict_tools(
            messages=messages,
            tools=tools,
        )
        self.completed += 1
        return result


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


def _usage(raw_responses: list[dict[str, Any]]) -> dict[str, int]:
    totals = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }
    for response in raw_responses:
        usage = response.get("usage")
        if not isinstance(usage, dict):
            continue
        for key in totals:
            value = usage.get(key)
            if isinstance(value, int):
                totals[key] += value
    return totals


def _serialize_outcome(
    outcome: AgentTurnOutcomeV2,
) -> dict[str, Any]:
    return {
        "status": outcome.status,
        "session_id": outcome.session_id,
        "turn_id": outcome.turn_id,
        "original_question": outcome.original_question,
        "model_response_count": outcome.model_response_count,
        "decision": (
            None
            if outcome.decision is None
            else outcome.decision.model_dump(mode="json")
        ),
        "tool_calls": [
            {
                "call_id": call.call_id,
                "provider_call_id": call.provider_call_id,
                "tool_name": call.tool_name,
                "arguments": call.arguments,
                "result_path": call.result_path,
            }
            for call in outcome.tool_calls
        ],
        "facts": [
            fact.model_dump(mode="json") for fact in outcome.facts
        ],
        "charts": [
            chart.model_dump(mode="json") for chart in outcome.charts
        ],
        "report_response": (
            None
            if outcome.report_response is None
            else outcome.report_response.model_dump(mode="json")
        ),
        "finalized_report": (
            None
            if outcome.finalized_report is None
            else outcome.finalized_report.model_dump(mode="json")
        ),
        "report_markdown": outcome.report_markdown,
        "report_validation": (
            None
            if outcome.report_validation is None
            else outcome.report_validation.model_dump(mode="json")
        ),
        "error_stage": outcome.error_stage,
        "error_message": outcome.error_message,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--approved-model-responses",
        type=int,
        required=True,
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
        raise SystemExit("未提供V2真实模型调用确认文本，已停止。")
    if args.approved_model_responses != (
        AUTHORIZED_RESPONSE_UPPER_BOUND
    ):
        raise SystemExit("本入口只允许本轮已授权的六次响应上限。")
    api_key = os.environ.get("LLM_API_KEY") or _load_dotenv_value(
        REPOSITORY_ROOT / ".env",
        "LLM_API_KEY",
    )
    if not api_key:
        raise SystemExit("缺少LLM_API_KEY，未发起真实调用。")
    if not WORKBOOK_PATH.exists():
        raise SystemExit("缺少本地Online Retail工作簿。")

    questions = load_frozen_questions()
    frame, _ = read_online_retail_workbook(WORKBOOK_PATH)
    registry = RetailToolRegistry(
        RetailToolService(build_retail_data_layers(frame))
    )
    approved_client = ApprovedV2Client(
        DeepSeekChatClient(api_key=api_key),
        AUTHORIZED_RESPONSE_UPPER_BOUND,
    )
    orchestrator = RetailAgentOrchestratorV2(
        client=approved_client,
        registry=registry,
    )
    run_id = datetime.now().astimezone().strftime(
        "agent_v2_online_%Y%m%dT%H%M%S_%f%z"
    )
    relative_root = f"results/raw/{run_id}"
    output_root = PROJECT_ROOT / relative_root
    session_id = _session_id_for_run(run_id)
    results = []
    all_raw_responses: list[dict[str, Any]] = []

    for index, question_id in enumerate(QUESTION_IDS, start=1):
        turn_id = f"TURN-{index:03d}"
        outcome = orchestrator.run_turn(
            session_id=session_id,
            turn_id=turn_id,
            question=questions[question_id]["question"],
            result_root=relative_root,
        )
        validation = validate_fixed_question(question_id, outcome)
        turn_root = output_root / turn_id
        raw_responses = list(outcome.raw_responses)
        all_raw_responses.extend(raw_responses)
        _write_json(turn_root / "raw_responses.json", raw_responses)
        _write_json(
            turn_root / "outcome.json",
            _serialize_outcome(outcome),
        )
        _write_json(
            turn_root / "fixed_question_validation.json",
            validation.model_dump(mode="json"),
        )
        if outcome.report_markdown is not None:
            (turn_root / "report.md").write_text(
                outcome.report_markdown,
                encoding="utf-8",
            )
        for call in outcome.tool_calls:
            _write_json(PROJECT_ROOT / call.result_path, call.result)
        result = {
            "question_id": question_id,
            "turn_id": turn_id,
            "outcome_status": outcome.status,
            "model_responses": outcome.model_response_count,
            "tool_sequence": [
                call.tool_name for call in outcome.tool_calls
            ],
            "fact_count": len(outcome.facts),
            "chart_count": len(outcome.charts),
            "report_validation_status": (
                None
                if outcome.report_validation is None
                else outcome.report_validation.status
            ),
            "fixed_question_status": validation.status,
            "issues": [
                issue.model_dump(mode="json")
                for issue in validation.issues
            ],
            "manual_review_items": validation.manual_review_items,
            "error_stage": outcome.error_stage,
            "error_message": outcome.error_message,
        }
        results.append(result)
        print(
            json.dumps(
                {
                    "progress": result,
                    "requests_attempted": approved_client.attempted,
                    "responses_completed": approved_client.completed,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

    usage = _usage(all_raw_responses)
    summary = {
        "schema_version": "1.5.6-h3-v2-online-validation-v1",
        "run_id": run_id,
        "created_at": _timestamp(),
        "execution_mode": "online_agent_v2_validation",
        "model": DEEPSEEK_MODEL,
        "question_ids": list(QUESTION_IDS),
        "approved_model_response_upper_bound": (
            AUTHORIZED_RESPONSE_UPPER_BOUND
        ),
        "model_requests_attempted": approved_client.attempted,
        "model_responses_completed": approved_client.completed,
        "authorization_upper_bound_not_exceeded": (
            approved_client.attempted
            <= AUTHORIZED_RESPONSE_UPPER_BOUND
        ),
        "usage": usage,
        "passed": sum(
            result["fixed_question_status"] == "passed"
            for result in results
        ),
        "failed": sum(
            result["fixed_question_status"] == "failed"
            for result in results
        ),
        "results": results,
        "privacy_assertions": {
            "api_key_saved": False,
            "authorization_header_saved": False,
            "raw_retail_rows_sent": False,
            "customer_id_values_sent": False,
            "absolute_paths_saved": False,
        },
    }
    _write_json(output_root / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
