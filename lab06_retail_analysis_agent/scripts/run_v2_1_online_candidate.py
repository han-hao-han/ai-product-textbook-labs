"""Explicitly authorized real-model runner for the V2.1 candidate."""

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

from src.agent_orchestrator_v2_1 import (  # noqa: E402
    AgentTurnOutcomeV2_1,
    RetailAgentOrchestratorV2_1,
)
from src.data_audit import read_online_retail_workbook  # noqa: E402
from src.deepseek_client import (  # noqa: E402
    DEEPSEEK_MODEL,
    DeepSeekChatClient,
)
from src.fixed_question_validation import (  # noqa: E402
    load_frozen_questions,
    validate_fixed_question,
)
from src.online_candidate_v2_1 import (  # noqa: E402
    REAL_MODEL_CONFIRMATION_V2_1,
    ResponseLimitedClientV2_1,
    validate_real_model_authorization_v2_1,
)
from src.retail_cleaning import build_retail_data_layers  # noqa: E402
from src.retail_tools import RetailToolService  # noqa: E402
from src.tool_registry import RetailToolRegistry  # noqa: E402


WORKBOOK_PATH = PROJECT_ROOT / "data" / "raw" / "Online Retail.xlsx"
ALL_QUESTION_IDS = tuple(
    f"Q{index:02d}" for index in range(1, 11)
)
RECIPE_ENTRY_RETIRED = True


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


def _session_id(run_id: str) -> str:
    return "SESSION-" + re.sub(r"[^A-Za-z0-9_-]", "_", run_id)


def _serialize_outcome(
    outcome: AgentTurnOutcomeV2_1,
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
                "dependency_fact_ids": list(
                    call.dependency_fact_ids
                ),
            }
            for call in outcome.tool_calls
        ],
        "facts": [
            fact.model_dump(mode="json") for fact in outcome.facts
        ],
        "report_plan": (
            None
            if outcome.report_plan is None
            else outcome.report_plan.model_dump(mode="json")
        ),
        "report_validation": (
            None
            if outcome.report_validation is None
            else outcome.report_validation.model_dump(mode="json")
        ),
        "report_markdown": outcome.report_markdown,
        "error_stage": outcome.error_stage,
        "error_message": outcome.error_message,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "调用DeepSeek V2.1在线候选；默认不会运行，"
            "必须同时提供固定问题、响应上限和确认文本。"
        )
    )
    parser.add_argument(
        "--question-ids",
        nargs="+",
        choices=ALL_QUESTION_IDS,
        required=True,
    )
    parser.add_argument(
        "--approved-model-responses",
        type=int,
        required=True,
    )
    parser.add_argument(
        "--confirm-real-model-calls",
        required=True,
        help=f"必须填写：{REAL_MODEL_CONFIRMATION_V2_1}",
    )
    return parser.parse_args()


def main() -> int:
    if RECIPE_ENTRY_RETIRED:
        raise SystemExit(
            "旧V2.1 recipe在线入口已因工具调用Agent主线重新打开而停用；"
            "请等待独立原生工具编排器和新的调用上限完成验证。"
            "未发起真实调用。"
        )
    args = parse_args()
    question_ids = tuple(dict.fromkeys(args.question_ids))
    try:
        validate_real_model_authorization_v2_1(
            confirmation=args.confirm_real_model_calls,
            approved_model_responses=(
                args.approved_model_responses
            ),
            question_count=len(question_ids),
        )
    except ValueError as exc:
        raise SystemExit(f"{exc}，未发起真实调用。") from exc

    api_key = os.environ.get("LLM_API_KEY") or _load_dotenv_value(
        REPOSITORY_ROOT / ".env",
        "LLM_API_KEY",
    )
    if not api_key:
        raise SystemExit("缺少LLM_API_KEY，未发起真实调用。")
    if not WORKBOOK_PATH.exists():
        raise SystemExit("缺少本地Online Retail工作簿，未发起真实调用。")

    questions = load_frozen_questions()
    frame, _ = read_online_retail_workbook(WORKBOOK_PATH)
    registry = RetailToolRegistry(
        RetailToolService(build_retail_data_layers(frame))
    )
    limited_client = ResponseLimitedClientV2_1(
        DeepSeekChatClient(api_key=api_key),
        limit=args.approved_model_responses,
    )
    orchestrator = RetailAgentOrchestratorV2_1(
        client=limited_client,
        registry=registry,
    )
    run_id = datetime.now().astimezone().strftime(
        "agent_v2_1_online_%Y%m%dT%H%M%S_%f%z"
    )
    relative_root = f"results/raw/{run_id}"
    output_root = PROJECT_ROOT / relative_root
    session_id = _session_id(run_id)
    results: list[dict[str, Any]] = []
    raw_responses: list[dict[str, Any]] = []

    for index, question_id in enumerate(question_ids, start=1):
        turn_id = f"TURN-{index:03d}"
        outcome = orchestrator.run_turn(
            session_id=session_id,
            turn_id=turn_id,
            question=questions[question_id]["question"],
            result_root=relative_root,
        )
        validation = validate_fixed_question(question_id, outcome)
        turn_root = output_root / turn_id
        turn_raw = list(outcome.raw_responses)
        raw_responses.extend(turn_raw)
        _write_json(
            turn_root / "provider_raw_responses.json",
            turn_raw,
        )
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
        results.append(
            {
                "question_id": question_id,
                "outcome_status": outcome.status,
                "fixed_question_status": validation.status,
                "model_response_count": outcome.model_response_count,
                "tool_sequence": [
                    call.tool_name for call in outcome.tool_calls
                ],
                "fact_count": len(outcome.facts),
                "report_validation_status": (
                    None
                    if outcome.report_validation is None
                    else outcome.report_validation.status
                ),
                "error_stage": outcome.error_stage,
                "error_message": outcome.error_message,
            }
        )

    usage = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }
    for response in raw_responses:
        response_usage = response.get("usage")
        if not isinstance(response_usage, dict):
            continue
        for key in usage:
            value = response_usage.get(key)
            if isinstance(value, int):
                usage[key] += value
    snapshot = limited_client.snapshot()
    summary = {
        "schema_version": "1.5.6-h3-v2.1-online-candidate-v1",
        "run_id": run_id,
        "execution_mode": "online_agent_v2_1_candidate",
        "model": DEEPSEEK_MODEL,
        "question_ids": list(question_ids),
        "approved_model_response_upper_bound": snapshot.limit,
        "model_requests_attempted": snapshot.attempted,
        "model_responses_completed": snapshot.completed,
        "model_transport_failures": snapshot.failed,
        "authorization_upper_bound_not_exceeded": (
            snapshot.attempted <= snapshot.limit
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
