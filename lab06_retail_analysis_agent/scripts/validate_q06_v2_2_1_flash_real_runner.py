"""Offline safety acceptance for the V2.2.1 Q06 Flash runner."""

from __future__ import annotations

import json
import sys
from argparse import Namespace
from copy import deepcopy
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import run_q06_v2_2_1_flash_real_revalidation as runner  # noqa: E402
from src.deepseek_client import ChatCompletionResult, ProviderToolCall  # noqa: E402
from src.deepseek_provider_schema_adapter_v2_1_revision import (  # noqa: E402
    DEEPSEEK_NONE_SENTINEL,
)
from src.mock_h2_registry import FrozenH2MockRegistry  # noqa: E402
from src.native_tool_transport_mock_v2_1_revision import (  # noqa: E402
    OfflineNativeToolTransportV2_1Revision,
)
from src.q06_provider_schema_revalidation_mock import (  # noqa: E402
    Q06ProviderSchemaRevalidationMockClient,
)
from src.q06_v2_2_1_flash_real_revalidation_plan import (  # noqa: E402
    load_q06_v2_2_1_flash_real_plan,
)


class InvalidFirstResponseClient:
    def complete_strict_tools(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: str = "auto",
    ) -> ChatCompletionResult:
        return ChatCompletionResult(
            finish_reason="tool_calls",
            content=None,
            tool_calls=(
                ProviderToolCall(
                    provider_call_id="offline-v221-invalid-first",
                    tool_name="analyze_time_trend",
                    arguments={
                        "period": "complete_months_only",
                        "start_date": DEEPSEEK_NONE_SENTINEL,
                        "end_date": DEEPSEEK_NONE_SENTINEL,
                        "grain": "monthly",
                        "metric": "sales_amount",
                        "exclude_incomplete_periods": True,
                    },
                ),
            ),
            raw_response={
                "offline_mock": True,
                "model": "deepseek-v4-flash",
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 20,
                    "total_tokens": 120,
                },
            },
            usage={
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "total_tokens": 120,
            },
        )


class LengthTerminalResponseClient:
    def __init__(self) -> None:
        self.delegate = Q06ProviderSchemaRevalidationMockClient()

    def complete_strict_tools(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: str = "auto",
    ) -> ChatCompletionResult:
        result = self.delegate.complete_strict_tools(
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
        )
        if sum(message.get("role") == "tool" for message in messages) == 2:
            return replace(result, finish_reason="length")
        return result


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def authorized_plan_copy() -> dict[str, Any]:
    plan = deepcopy(load_q06_v2_2_1_flash_real_plan())
    plan["status"] = (
        "frozen_guarded_runner_offline_validated_and_real_call_"
        "authorized_pending_execution"
    )
    plan["authorization"].update(
        {
            "status": "authorized_by_user",
            "real_model_calls_allowed": True,
            "authorization_matches_frozen_plan": True,
            "authorized_question_ids": ["Q06"],
            "authorized_model": "deepseek-v4-flash",
            "authorized_response_attempt_upper_bound": 3,
            "authorized_automatic_retry_count": 0,
        }
    )
    plan["implementation"].update(
        {
            "guarded_runner": (
                "scripts/run_q06_v2_2_1_flash_real_revalidation.py"
            ),
            "guarded_runner_status": "implemented_and_offline_validated",
        }
    )
    plan["runner_offline_validation"] = {
        "status": "passed",
        "current_gate_blocked_before_api_key_read": True,
        "success_response_attempts": 3,
        "success_tool_choices": ["auto", "auto", "none"],
        "success_response_formats": [
            None,
            None,
            {"type": "json_object"},
        ],
        "failure_response_attempts": 1,
        "privacy_evidence_guard_passed": True,
        "real_network_opened": False,
        "api_key_read_from_environment": False,
        "real_model_called": False,
    }
    return plan


def exact_args() -> Namespace:
    return Namespace(
        question_id="Q06",
        approved_model_responses=3,
        automatic_retries=0,
        confirm_real_model_calls=runner.CONFIRMATION,
    )


def _run_case(
    *,
    logical_client: Any,
    api_key: str,
    output_dir: Path,
    run_id: str,
) -> tuple[Any, OfflineNativeToolTransportV2_1Revision]:
    transport = OfflineNativeToolTransportV2_1Revision(
        logical_client,
        expected_model="deepseek-v4-flash",
    )
    result = runner.execute_v2_2_1_validation(
        api_key=api_key,
        registry=FrozenH2MockRegistry(),
        transport=transport,
        output_parent=output_dir,
        run_id=run_id,
    )
    return result, transport


def main() -> int:
    timestamp = datetime.now().astimezone().strftime(
        "%Y%m%dT%H%M%S_%f%z"
    )
    run_id = f"q06_v2_2_1_flash_runner_offline_{timestamp}"
    output_dir = PROJECT_ROOT / "results" / "raw" / run_id
    output_dir.mkdir(parents=True, exist_ok=False)

    current_gate_blocked = False
    try:
        runner.validate_execution_request(exact_args())
    except ValueError:
        current_gate_blocked = True
    future_authority = runner.validate_execution_request(
        exact_args(),
        plan=authorized_plan_copy(),
    )

    success, success_transport = _run_case(
        logical_client=Q06ProviderSchemaRevalidationMockClient(),
        api_key="offline-v221-success-key",
        output_dir=output_dir,
        run_id="success",
    )
    first_failure, first_failure_transport = _run_case(
        logical_client=InvalidFirstResponseClient(),
        api_key="offline-v221-first-failure-key",
        output_dir=output_dir,
        run_id="first_failure",
    )
    length_failure, length_transport = _run_case(
        logical_client=LengthTerminalResponseClient(),
        api_key="offline-v221-length-key",
        output_dir=output_dir,
        run_id="length_failure",
    )

    evidence_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in output_dir.rglob("*.json")
    )
    privacy_passed = not any(
        marker in evidence_text
        for marker in (
            "offline-v221-success-key",
            "offline-v221-first-failure-key",
            "offline-v221-length-key",
            "Bearer ",
            '"Authorization"',
        )
    )
    response_formats = [
        request.response_format for request in success_transport.requests
    ]
    summary = {
        "schema_version": (
            "1.5.6-h3-q06-v2.2.1-flash-runner-offline-v1"
        ),
        "run_id": run_id,
        "status": "pending",
        "current_gate_blocked_before_api_key_read": current_gate_blocked,
        "future_exact_authority_model": future_authority.model,
        "success": {
            "passed": success.passed,
            "response_attempts": success.summary[
                "actual_model_response_attempts"
            ],
            "transport_requests": len(success_transport.requests),
            "tool_choices": [
                request.tool_choice for request in success_transport.requests
            ],
            "response_formats": response_formats,
            "tool_sequence": [
                call["tool_name"]
                for call in success.case_payload["outcome"]["tool_calls"]
            ],
            "chart_count": len(success.case_payload["outcome"]["charts"]),
            "report_validation_status": success.case_payload["outcome"][
                "report_validation"
            ]["status"],
            "evidence_files": ["success/Q06.json", "success/summary.json"],
        },
        "first_failure": {
            "passed": first_failure.passed,
            "response_attempts": first_failure.summary[
                "actual_model_response_attempts"
            ],
            "transport_requests": len(first_failure_transport.requests),
            "tool_calls_executed": len(
                first_failure.case_payload["outcome"]["tool_calls"]
            ),
            "evidence_files": [
                "first_failure/Q06.json",
                "first_failure/summary.json",
            ],
        },
        "length_failure": {
            "passed": length_failure.passed,
            "response_attempts": length_failure.summary[
                "actual_model_response_attempts"
            ],
            "transport_requests": len(length_transport.requests),
            "program_failures": length_failure.case_payload[
                "program_failures"
            ],
            "evidence_files": [
                "length_failure/Q06.json",
                "length_failure/summary.json",
            ],
        },
        "privacy_evidence_guard_passed": privacy_passed,
        "real_network_opened": False,
        "api_key_read_from_environment": False,
        "real_model_called": False,
        "real_model_calls_allowed": False,
    }
    passed = (
        current_gate_blocked
        and future_authority.model == "deepseek-v4-flash"
        and success.passed
        and summary["success"]["response_attempts"] == 3
        and summary["success"]["tool_choices"]
        == ["auto", "auto", "none"]
        and response_formats == runner.REQUIRED_RESPONSE_FORMATS
        and summary["success"]["chart_count"] == 2
        and summary["success"]["report_validation_status"] == "passed"
        and not first_failure.passed
        and summary["first_failure"]["response_attempts"] == 1
        and summary["first_failure"]["transport_requests"] == 1
        and summary["first_failure"]["tool_calls_executed"] == 0
        and not length_failure.passed
        and summary["length_failure"]["response_attempts"] == 3
        and "provider_finish_reason_length"
        in summary["length_failure"]["program_failures"]
        and privacy_passed
    )
    summary["status"] = "passed" if passed else "failed"
    _write_json(output_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
