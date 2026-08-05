"""Offline acceptance for the V2.2 Q06 Flash guarded real runner."""

from __future__ import annotations

import json
import sys
from argparse import Namespace
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import run_q06_v2_2_flash_real_revalidation as runner  # noqa: E402
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
from src.q06_v2_2_flash_real_revalidation_plan import (  # noqa: E402
    load_q06_v2_2_flash_real_plan,
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
                    provider_call_id="offline-v22-invalid-first",
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


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _authorized_copy() -> dict[str, Any]:
    plan = deepcopy(load_q06_v2_2_flash_real_plan())
    plan["status"] = (
        "frozen_guarded_runner_offline_validated_and_real_call_"
        "authorized_pending_execution"
    )
    plan["authorization"].update(
        {
            "status": "authorized_by_user",
            "real_model_calls_allowed": True,
            "authorization_matches_frozen_plan": True,
        }
    )
    plan["implementation"]["guarded_runner_status"] = (
        "implemented_and_offline_validated"
    )
    return plan


def main() -> int:
    timestamp = datetime.now().astimezone().strftime(
        "%Y%m%dT%H%M%S_%f%z"
    )
    run_id = f"q06_v2_2_flash_runner_offline_validation_{timestamp}"
    output_dir = PROJECT_ROOT / "results" / "raw" / run_id
    output_dir.mkdir(parents=True, exist_ok=False)

    exact_args = Namespace(
        question_id="Q06",
        approved_model_responses=3,
        automatic_retries=0,
        confirm_real_model_calls=runner.CONFIRMATION,
    )
    current_gate_blocked = False
    try:
        runner.validate_execution_request(exact_args)
    except ValueError:
        current_gate_blocked = True
    future_authority = runner.validate_execution_request(
        exact_args,
        plan=_authorized_copy(),
    )

    success_transport = OfflineNativeToolTransportV2_1Revision(
        Q06ProviderSchemaRevalidationMockClient(),
        expected_model="deepseek-v4-flash",
    )
    success = runner.execute_v2_2_validation(
        api_key="offline-v22-success-key",
        registry=FrozenH2MockRegistry(),
        transport=success_transport,
        output_parent=output_dir,
        run_id="success",
    )

    failure_transport = OfflineNativeToolTransportV2_1Revision(
        InvalidFirstResponseClient(),
        expected_model="deepseek-v4-flash",
    )
    failure = runner.execute_v2_2_validation(
        api_key="offline-v22-failure-key",
        registry=FrozenH2MockRegistry(),
        transport=failure_transport,
        output_parent=output_dir,
        run_id="failure",
    )

    evidence_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in output_dir.rglob("*.json")
    )
    privacy_passed = not any(
        marker in evidence_text
        for marker in (
            "offline-v22-success-key",
            "offline-v22-failure-key",
            "Bearer ",
            '"Authorization"',
        )
    )
    summary = {
        "schema_version": "1.5.6-h3-q06-v2.2-flash-runner-offline-v1",
        "run_id": run_id,
        "status": "passed",
        "current_candidate_gate_blocked_before_api_key_read": current_gate_blocked,
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
        "failure": {
            "passed": failure.passed,
            "response_attempts": failure.summary[
                "actual_model_response_attempts"
            ],
            "transport_requests": len(failure_transport.requests),
            "tool_calls_executed": len(
                failure.case_payload["outcome"]["tool_calls"]
            ),
            "program_failures": failure.case_payload["program_failures"],
            "evidence_files": ["failure/Q06.json", "failure/summary.json"],
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
        and summary["success"]["chart_count"] == 2
        and summary["success"]["report_validation_status"] == "passed"
        and not failure.passed
        and summary["failure"]["response_attempts"] == 1
        and summary["failure"]["transport_requests"] == 1
        and summary["failure"]["tool_calls_executed"] == 0
        and privacy_passed
    )
    summary["status"] = "passed" if passed else "failed"
    _write_json(output_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
