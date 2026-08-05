"""Offline acceptance for the guarded single-Q06 runner."""

from __future__ import annotations

import json
import sys
from argparse import Namespace
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import run_q06_real_revalidation_v2_1_revision as runner  # noqa: E402
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


class InvalidFirstQ06ResponseClient:
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
                    provider_call_id="offline-invalid-first",
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
            raw_response={"offline_invalid_first": True},
            usage=None,
        )


def main() -> int:
    timestamp = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S_%f%z")
    run_id = f"q06_real_runner_offline_validation_{timestamp}"
    output_root = PROJECT_ROOT / "results" / "raw" / run_id

    exact_args = Namespace(
        question_id="Q06",
        approved_model_responses=3,
        automatic_retries=0,
        confirm_real_model_calls=runner.Q06_REAL_REVALIDATION_CONFIRMATION,
    )
    authorization_gate_blocked = False
    authorization_error = None
    try:
        runner.validate_execution_request(exact_args)
    except ValueError as exc:
        authorization_gate_blocked = True
        authorization_error = str(exc)

    core_real_transport_blocked = False
    core_real_transport_error = None
    try:
        runner.execute_q06_validation(
            api_key="offline-core-guard-placeholder",
            registry=FrozenH2MockRegistry(),
            transport=None,
            output_parent=output_root,
            run_id="must-not-run",
        )
    except ValueError as exc:
        core_real_transport_blocked = True
        core_real_transport_error = str(exc)

    success_transport = OfflineNativeToolTransportV2_1Revision(
        Q06ProviderSchemaRevalidationMockClient(),
        expected_model="deepseek-v4-pro",
    )
    success = runner.execute_q06_validation(
        api_key="offline-runner-success-placeholder",
        registry=FrozenH2MockRegistry(),
        transport=success_transport,
        output_parent=output_root,
        run_id="success",
    )

    failure_transport = OfflineNativeToolTransportV2_1Revision(
        InvalidFirstQ06ResponseClient(),
        expected_model="deepseek-v4-pro",
    )
    failure = runner.execute_q06_validation(
        api_key="offline-runner-failure-placeholder",
        registry=FrozenH2MockRegistry(),
        transport=failure_transport,
        output_parent=output_root,
        run_id="failure",
    )

    privacy_guard_passed = False
    try:
        runner._safe_json_text(
            {"Authorization": "Bearer forbidden"},
            api_key="unrelated-placeholder",
        )
    except ValueError:
        privacy_guard_passed = True

    success_files = sorted(path.name for path in success.output_dir.iterdir())
    failure_files = sorted(path.name for path in failure.output_dir.iterdir())
    passed = (
        authorization_gate_blocked
        and core_real_transport_blocked
        and success.passed
        and success.summary["actual_model_response_attempts"] == 3
        and success.case_payload["usage"]["responses_with_usage"] == 3
        and len(success_transport.requests) == 3
        and not failure.passed
        and failure.summary["actual_model_response_attempts"] == 1
        and failure.case_payload["usage"]["responses_with_usage"] == 1
        and len(failure_transport.requests) == 1
        and len(failure.case_payload["outcome"]["raw_responses"]) == 1
        and failure.case_payload["outcome"]["tool_calls"] == []
        and success_files == ["Q06.json", "summary.json"]
        and failure_files == ["Q06.json", "summary.json"]
        and privacy_guard_passed
    )
    summary = {
        "schema_version": "1.5.6-h3-q06-real-runner-offline-validation-v1",
        "run_id": run_id,
        "status": "passed" if passed else "failed",
        "real_network_opened": False,
        "api_key_read_from_environment": False,
        "real_model_called": False,
        "real_model_calls_allowed": False,
        "authorization_gate": {
            "exact_request_blocked_before_key_read": authorization_gate_blocked,
            "error": authorization_error,
            "core_real_transport_blocked_without_validated_authority": (
                core_real_transport_blocked
            ),
            "core_error": core_real_transport_error,
        },
        "success_path": {
            "response_attempts": success.summary[
                "actual_model_response_attempts"
            ],
            "transport_requests": len(success_transport.requests),
            "program_validation_status": success.summary[
                "program_validation_status"
            ],
            "evidence_files": success_files,
            "provider_raw_response_count": len(
                success.case_payload["outcome"]["raw_responses"]
            ),
            "provider_usage_response_count": success.case_payload["usage"][
                "responses_with_usage"
            ],
        },
        "failure_path": {
            "response_attempts": failure.summary[
                "actual_model_response_attempts"
            ],
            "transport_requests": len(failure_transport.requests),
            "program_validation_status": failure.summary[
                "program_validation_status"
            ],
            "evidence_files": failure_files,
            "provider_raw_response_count": len(
                failure.case_payload["outcome"]["raw_responses"]
            ),
            "provider_usage_response_count": failure.case_payload["usage"][
                "responses_with_usage"
            ],
            "tool_calls_executed": len(
                failure.case_payload["outcome"]["tool_calls"]
            ),
            "observed_invalid_grain": failure.case_payload[
                "native_model_trace"
            ][0]["selected_arguments"]["grain"],
        },
        "privacy_evidence_guard_passed": privacy_guard_passed,
        "next_gate": "等待用户单独授权Q06、deepseek-v4-pro、最多3次响应、自动重试0",
    }
    (output_root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {**summary, "output_dir": str(output_root)},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
