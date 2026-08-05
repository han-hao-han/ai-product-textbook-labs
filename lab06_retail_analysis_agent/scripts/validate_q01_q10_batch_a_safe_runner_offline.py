"""Formal offline validation for the frozen batch-A safe runner."""

from __future__ import annotations

import json
import sys
from argparse import Namespace
from datetime import datetime
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import run_q01_q10_batch_a_flash_validation as entry  # noqa: E402
from src.deepseek_client import (  # noqa: E402
    ChatCompletionResult,
    DeepSeekClientError,
    ProviderToolCall,
)
from src.mock_h2_registry import FrozenH2MockRegistry  # noqa: E402
from src.mock_native_tool_client_v2_1_revision import _tool_payloads  # noqa: E402
from src.native_tool_transport_mock_v2_1_revision import (  # noqa: E402
    OfflineNativeToolTransportV2_1Revision,
)
from src.online_native_tool_candidate_v2_1_revision import (  # noqa: E402
    ResponseLimitedStrictNativeClient,
)
from src.q01_q10_batch_a_offline_mock import (  # noqa: E402
    BatchAEvidenceCompleteMockClient,
)
from src.q01_q10_batch_a_safe_runner import (  # noqa: E402
    BATCH_A_OFFLINE_CONFIRMATION,
    BATCH_A_QUESTION_IDS,
    execute_batch_a_validation,
    validate_batch_a_runner_implementation,
    validate_offline_execution_request,
)


class FailAtTransport:
    def __init__(self, delegate, *, fail_at: int) -> None:
        self.delegate = delegate
        self.fail_at = fail_at
        self.attempted = 0

    def __call__(self, url, body, headers, timeout_seconds):
        self.attempted += 1
        if self.attempted == self.fail_at:
            raise DeepSeekClientError("offline injected network interruption")
        return self.delegate(url, body, headers, timeout_seconds)

    def audit_payload(self):
        payload = self.delegate.audit_payload()
        payload["injected_transport_attempts"] = self.attempted
        payload["injected_failure_at"] = self.fail_at
        return payload


class WrongQ06SecondArgumentsClient(BatchAEvidenceCompleteMockClient):
    def complete_strict_tools(self, **kwargs):
        result = super().complete_strict_tools(**kwargs)
        if len(_tool_payloads(kwargs["messages"])) != 1 or not result.tool_calls:
            return result
        call = result.tool_calls[0]
        if call.tool_name != "rank_products":
            return result
        arguments = dict(call.arguments)
        arguments["top_n"] = 4
        return ChatCompletionResult(
            finish_reason=result.finish_reason,
            content=result.content,
            tool_calls=(
                ProviderToolCall(
                    provider_call_id=call.provider_call_id,
                    tool_name=call.tool_name,
                    arguments=arguments,
                ),
            ),
            raw_response=result.raw_response,
            usage=result.usage,
        )


def _transport(client=None):
    return OfflineNativeToolTransportV2_1Revision(
        client or BatchAEvidenceCompleteMockClient(),
        expected_model="deepseek-v4-flash",
        terminal_question_ids=BATCH_A_QUESTION_IDS,
        terminal_json_question_ids=BATCH_A_QUESTION_IDS,
    )


def _authority():
    return validate_offline_execution_request(
        confirmation=BATCH_A_OFFLINE_CONFIRMATION
    )


def _execute(output_dir: Path, name: str, transport):
    return execute_batch_a_validation(
        api_key=f"offline-{name}-placeholder-secret",
        registry=FrozenH2MockRegistry(),
        transport=transport,
        authority=_authority(),
        output_parent=output_dir,
        run_id=name,
    )


def _evidence_is_safe(path: Path, secret: str) -> bool:
    text = "\n".join(
        item.read_text(encoding="utf-8") for item in path.rglob("*.json")
    )
    return (
        secret not in text
        and '"Authorization"' not in text
        and "Bearer " not in text
        and not __import__("re").search(
            r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]", text
        )
    )


def _authorization_gate_probe() -> dict[str, bool | str]:
    args = Namespace(
        batch_id="A",
        question_id=list(BATCH_A_QUESTION_IDS),
        model="deepseek-v4-flash",
        approved_model_responses=8,
        automatic_retries=0,
        confirm_real_model_calls="I_AUTHORIZE_Q01_Q10_BATCH_A_FLASH_REAL_CALLS",
    )
    key_read = False

    def forbidden_key_read():
        nonlocal key_read
        key_read = True
        raise AssertionError("API key must not be read")

    error = ""
    with patch.object(entry, "parse_args", return_value=args), patch.object(
        entry, "_load_api_key", side_effect=forbidden_key_read
    ):
        try:
            entry.main()
        except SystemExit as exc:
            error = str(exc)
    return {
        "blocked": "authorization gate" in error,
        "api_key_read": key_read,
        "error_is_sanitized": "LLM_API_KEY" not in error and "Bearer " not in error,
    }


def _ninth_attempt_probe() -> dict[str, int | bool]:
    class CountingClient:
        def __init__(self) -> None:
            self.calls = 0

        def complete_strict_tools(self, **kwargs):
            self.calls += 1
            return ChatCompletionResult(
                finish_reason="stop",
                content="{}",
                tool_calls=(),
                raw_response={"offline": True},
                usage=None,
            )

    underlying = CountingClient()
    limited = ResponseLimitedStrictNativeClient(underlying, limit=8)
    for _ in range(8):
        limited.complete_strict_tools(messages=[], tools=[])
    blocked = False
    try:
        limited.complete_strict_tools(messages=[], tools=[])
    except DeepSeekClientError:
        blocked = True
    return {
        "ninth_attempt_blocked": blocked,
        "underlying_calls": underlying.calls,
        "reserved_attempts": limited.snapshot().attempted,
    }


def main() -> int:
    validate_batch_a_runner_implementation()
    timestamp = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S_%f%z")
    run_id = f"q01_q10_batch_a_safe_runner_offline_{timestamp}"
    output_dir = PROJECT_ROOT / "results" / "raw" / run_id

    authorization = _authorization_gate_probe()
    success_transport = _transport()
    success = _execute(output_dir, "success", success_transport)
    network_transport = FailAtTransport(_transport(), fail_at=3)
    network = _execute(output_dir, "network_failure", network_transport)
    semantic = _execute(
        output_dir,
        "semantic_failure",
        _transport(WrongQ06SecondArgumentsClient()),
    )
    ninth = _ninth_attempt_probe()

    success_safe = _evidence_is_safe(
        success.output_dir, "offline-success-placeholder-secret"
    )
    failure_safe = _evidence_is_safe(
        network.output_dir, "offline-network_failure-placeholder-secret"
    ) and _evidence_is_safe(
        semantic.output_dir, "offline-semantic_failure-placeholder-secret"
    )
    passed = (
        authorization["blocked"] is True
        and authorization["api_key_read"] is False
        and success.passed
        and success.summary["actual_response_attempts"] == 8
        and success.summary["completed_model_responses"] == 8
        and success.summary["failed_transport_or_provider_attempts"] == 0
        and network.passed is False
        and network.summary["actual_response_attempts"] == 3
        and network.summary["completed_model_responses"] == 2
        and network.summary["failed_transport_or_provider_attempts"] == 1
        and network.summary["question_ids_not_executed"] == ["Q08", "Q09", "Q10"]
        and semantic.passed is False
        and semantic.summary["actual_response_attempts"] == 4
        and semantic.summary["completed_model_responses"] == 4
        and semantic.summary["question_ids_not_executed"] == ["Q08", "Q09", "Q10"]
        and ninth["ninth_attempt_blocked"] is True
        and ninth["underlying_calls"] == 8
        and success_safe
        and failure_safe
    )
    summary = {
        "schema_version": "1.5.6-h3-q01-q10-batch-a-safe-runner-offline-validation-v1",
        "run_id": run_id,
        "status": "passed" if passed else "failed",
        "execution_mode": "offline_injected_transport",
        "model": "deepseek-v4-flash",
        "question_ids": list(BATCH_A_QUESTION_IDS),
        "response_attempt_upper_bound": 8,
        "automatic_retry_count": 0,
        "authorization_gate": authorization,
        "success_scenario": success.summary,
        "network_failure_scenario": network.summary,
        "semantic_failure_scenario": semantic.summary,
        "ninth_attempt_probe": ninth,
        "evidence_safety": {
            "success_evidence_safe": success_safe,
            "failure_evidence_safe": failure_safe,
            "api_key_saved": False,
            "authorization_header_value_saved": False,
            "request_body_saved": False,
            "raw_customer_id_exported": False,
            "local_absolute_paths_saved": False,
        },
        "real_network_opened": False,
        "real_model_called": False,
        "api_key_read_from_environment": False,
        "real_model_calls_allowed": False,
        "v2_2_3_resumed": False,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
