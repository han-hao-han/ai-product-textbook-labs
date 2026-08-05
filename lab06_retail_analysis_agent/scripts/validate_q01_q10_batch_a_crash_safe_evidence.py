"""Formal offline validation of batch-A crash-safe evidence boundaries."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from time import perf_counter


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.deepseek_client import (  # noqa: E402
    ChatCompletionResult,
    DeepSeekClientError,
    HttpResponseData,
)
from src.mock_h2_registry import FrozenH2MockRegistry  # noqa: E402
from src.native_tool_transport_mock_v2_1_revision import (  # noqa: E402
    OfflineNativeToolTransportV2_1Revision,
)
from src.online_native_tool_candidate_v2_1_revision import (  # noqa: E402
    ResponseLimitedStrictNativeClient,
)
from src.q01_q10_batch_a_crash_safe_evidence import (  # noqa: E402
    recover_batch_a_run_state,
    validate_crash_safe_evidence_boundary,
)
from src.q01_q10_batch_a_offline_mock import (  # noqa: E402
    BatchAEvidenceCompleteMockClient,
)
from src.q01_q10_batch_a_safe_runner import (  # noqa: E402
    BATCH_A_OFFLINE_CONFIRMATION,
    BATCH_A_QUESTION_IDS,
    BATCH_A_REQUEST_TIMEOUT_SECONDS,
    BATCH_A_TOTAL_TIMEOUT_SECONDS,
    execute_batch_a_validation,
    validate_offline_execution_request,
)


class SimulatedExternalTermination(BaseException):
    pass


class TerminatingTransport:
    def __call__(self, url, body, headers, timeout_seconds):
        raise SimulatedExternalTermination("simulated process termination")


class InvalidJsonTransport:
    def __call__(self, url, body, headers, timeout_seconds):
        return HttpResponseData(status_code=200, content=b"not-json")


def _authority():
    return validate_offline_execution_request(
        confirmation=BATCH_A_OFFLINE_CONFIRMATION
    )


def _execute(output_dir: Path, run_id: str, transport, secret: str):
    return execute_batch_a_validation(
        api_key=secret,
        registry=FrozenH2MockRegistry(),
        transport=transport,
        authority=_authority(),
        output_parent=output_dir,
        run_id=run_id,
    )


def _success_transport():
    return OfflineNativeToolTransportV2_1Revision(
        BatchAEvidenceCompleteMockClient(),
        expected_model="deepseek-v4-flash",
        terminal_question_ids=BATCH_A_QUESTION_IDS,
        terminal_json_question_ids=BATCH_A_QUESTION_IDS,
    )


def _deadline_probe() -> dict[str, object]:
    events: list[tuple[str, dict]] = []

    class CountingClient:
        timeout_seconds = 120.0

        def __init__(self) -> None:
            self.calls = 0
            self.response_event_sink = None

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
    limited = ResponseLimitedStrictNativeClient(
        underlying,
        limit=8,
        response_event_sink=lambda kind, payload: events.append(
            (kind, payload)
        ),
        batch_timeout_seconds=1.0,
        started_monotonic=perf_counter() - 2.0,
    )
    blocked = False
    try:
        limited.complete_strict_tools(messages=[], tools=[])
    except DeepSeekClientError:
        blocked = True
    return {
        "blocked_before_attempt": blocked,
        "underlying_calls": underlying.calls,
        "reserved_attempts": limited.snapshot().attempted,
        "event_types": [item[0] for item in events],
    }


def _safe_scan(output_dir: Path, secrets: list[str]) -> bool:
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in output_dir.rglob("*.json")
    )
    return (
        all(secret not in text for secret in secrets)
        and '"Authorization"' not in text
        and "Bearer " not in text
        and re.search(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]", text) is None
    )


def main() -> int:
    validate_crash_safe_evidence_boundary()
    timestamp = datetime.now().astimezone().strftime(
        "%Y%m%dT%H%M%S_%f%z"
    )
    run_id = f"q01_q10_batch_a_crash_safe_offline_{timestamp}"
    output_dir = PROJECT_ROOT / "results" / "raw" / run_id

    reservation_secret = "offline-crash-reservation-validation-secret"
    try:
        _execute(
            output_dir,
            "termination_after_reservation",
            TerminatingTransport(),
            reservation_secret,
        )
    except SimulatedExternalTermination:
        pass
    reservation = recover_batch_a_run_state(
        output_dir / "termination_after_reservation"
    )

    parse_secret = "offline-http-parse-validation-secret"
    parse_result = _execute(
        output_dir,
        "http_before_parse_failure",
        InvalidJsonTransport(),
        parse_secret,
    )
    parse_recovery = recover_batch_a_run_state(
        output_dir / "http_before_parse_failure"
    )

    success_secret = "offline-crash-success-validation-secret"
    success = _execute(
        output_dir,
        "complete_success",
        _success_transport(),
        success_secret,
    )
    success_recovery = recover_batch_a_run_state(
        output_dir / "complete_success"
    )
    deadline = _deadline_probe()
    temporary_files = [
        str(path.relative_to(output_dir)).replace("\\", "/")
        for path in output_dir.rglob("*.tmp")
    ]
    evidence_safe = _safe_scan(
        output_dir,
        [reservation_secret, parse_secret, success_secret],
    )
    passed = (
        reservation["reserved_attempts"] == 1
        and reservation["http_responses_received"] == 0
        and reservation["parsed_responses"] == 0
        and reservation["authorization_consumed"] is True
        and reservation["automatic_resume_allowed"] is False
        and parse_result.passed is False
        and parse_recovery["reserved_attempts"] == 1
        and parse_recovery["http_responses_received"] == 1
        and parse_recovery["parsed_responses"] == 0
        and success.passed
        and success_recovery["reserved_attempts"] == 8
        and success_recovery["http_responses_received"] == 8
        and success_recovery["parsed_responses"] == 8
        and deadline["blocked_before_attempt"] is True
        and deadline["underlying_calls"] == 0
        and deadline["reserved_attempts"] == 0
        and BATCH_A_TOTAL_TIMEOUT_SECONDS
        >= 8 * BATCH_A_REQUEST_TIMEOUT_SECONDS + 120
        and not temporary_files
        and evidence_safe
    )
    summary = {
        "schema_version": "1.5.6-h3-q01-q10-batch-a-crash-safe-offline-validation-v1",
        "run_id": run_id,
        "status": "passed" if passed else "failed",
        "execution_mode": "offline_injected_transport",
        "question_ids": list(BATCH_A_QUESTION_IDS),
        "model": "deepseek-v4-flash",
        "response_attempt_upper_bound": 8,
        "automatic_retry_count": 0,
        "time_boundaries": {
            "per_request_timeout_seconds": BATCH_A_REQUEST_TIMEOUT_SECONDS,
            "batch_internal_timeout_seconds": BATCH_A_TOTAL_TIMEOUT_SECONDS,
            "recommended_external_process_timeout_seconds": 1200,
        },
        "termination_after_reservation": reservation,
        "http_before_parse_failure": parse_recovery,
        "complete_success": success_recovery,
        "deadline_probe": deadline,
        "temporary_files_remaining": temporary_files,
        "evidence_safety_passed": evidence_safe,
        "automatic_resume_allowed": False,
        "new_user_authorization_required_after_recovery": True,
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
