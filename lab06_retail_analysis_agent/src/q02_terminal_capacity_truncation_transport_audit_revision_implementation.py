"""Offline implementation audit using the saved real Q02 provider responses."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.deepseek_client import ChatCompletionResult, ProviderToolCall
from src.fixed_question_validation import (
    load_frozen_questions,
    validate_fixed_question,
)
from src.mock_h2_registry import FrozenH2MockRegistry
from src.native_tool_agent_v2_1_revision import (
    RetailNativeToolAgentV2_1Revision,
)
from src.native_tool_transport_mock_v2_1_revision import (
    OfflineNativeToolTransportV2_1Revision,
)
from src.q01_q10_batch_a_offline_mock import BATCH_A_QUESTION_IDS
from src.q01_q10_batch_a_safe_runner import (
    BATCH_A_OFFLINE_CONFIRMATION,
    BATCH_A_RESPONSE_ATTEMPT_CAP,
    BATCH_A_AUTOMATIC_RETRIES,
    BATCH_A_MODEL,
    ValidatedBatchAExecutionAuthority,
    _safe_transport_audit,
    execute_batch_a_validation,
    validate_offline_execution_request,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAVED_Q02_CASE_PATH = (
    PROJECT_ROOT
    / "results"
    / "raw"
    / "q01_q10_batch_a_flash_20260803T223720_058350+0800"
    / "Q02.json"
)
SAVED_Q02_RUN_STATE_PATH = SAVED_Q02_CASE_PATH.parent / "run_state.json"
NOT_EVALUATED = "not_evaluated_due_to_terminal_output_truncation"


class Q02TerminalRevisionImplementationError(ValueError):
    """Raised when saved-response implementation evidence is inconsistent."""


def _saved_raw_responses() -> list[dict[str, Any]]:
    case = json.loads(SAVED_Q02_CASE_PATH.read_text(encoding="utf-8"))
    responses = case.get("outcome", {}).get("raw_responses")
    if not isinstance(responses, list) or len(responses) != 2:
        raise Q02TerminalRevisionImplementationError(
            "saved Q02 evidence must contain exactly two provider responses"
        )
    return responses


def _chat_result(raw: dict[str, Any]) -> ChatCompletionResult:
    choice = raw["choices"][0]
    message = choice["message"]
    calls = []
    for item in message.get("tool_calls") or []:
        function = item["function"]
        calls.append(
            ProviderToolCall(
                provider_call_id=str(item["id"]),
                tool_name=str(function["name"]),
                arguments=json.loads(function["arguments"]),
            )
        )
    return ChatCompletionResult(
        finish_reason=str(choice["finish_reason"]),
        content=message.get("content"),
        tool_calls=tuple(calls),
        raw_response=raw,
        usage=raw.get("usage"),
    )


class SavedQ02TruncatedClient:
    """Replay the exact saved model decisions without network access."""

    def __init__(self) -> None:
        self._responses = _saved_raw_responses()
        self.calls = 0

    def complete_strict_tools(self, **_: Any) -> ChatCompletionResult:
        if self.calls >= len(self._responses):
            raise Q02TerminalRevisionImplementationError(
                "saved Q02 replay attempted an unexpected extra response"
            )
        raw = self._responses[self.calls]
        self.calls += 1
        return _chat_result(raw)


@dataclass(frozen=True)
class Q02TerminalRevisionImplementationResult:
    passed: bool
    direct_outcome_status: str
    direct_error_stage: str | None
    direct_error_message: str | None
    direct_tool_names: tuple[str, ...]
    direct_response_count: int
    tool_reference_answer_status: str
    report_content_acceptance_status: str
    fixed_validation_issue_paths: tuple[str, ...]
    batch_primary_stop_stage: str | None
    batch_primary_stop_codes: tuple[str, ...]
    batch_acceptance_consequences: tuple[str, ...]
    batch_not_evaluated_checks: tuple[str, ...]
    batch_program_failures: tuple[str, ...]
    batch_evaluation_states: dict[str, str]
    request_max_tokens: tuple[int, ...]
    offline_transport_audit: dict[str, Any]
    saved_real_transport_audit_preview: dict[str, Any]
    real_model_called: bool
    network_used: bool
    api_key_read: bool


def compile_q02_terminal_revision_implementation(
) -> Q02TerminalRevisionImplementationResult:
    question = load_frozen_questions()["Q02"]["question"]
    direct_client = SavedQ02TruncatedClient()
    direct = RetailNativeToolAgentV2_1Revision(
        client=direct_client,
        registry=FrozenH2MockRegistry(),
        terminal_lock_question_ids=BATCH_A_QUESTION_IDS,
        terminal_json_question_ids=BATCH_A_QUESTION_IDS,
    ).run_turn(
        session_id="SESSION-q02-terminal-truncation-replay",
        turn_id="TURN-002",
        question=question,
        result_root="results/raw/q02_terminal_truncation_replay",
    )
    validation = validate_fixed_question("Q02", direct)

    transport = OfflineNativeToolTransportV2_1Revision(
        SavedQ02TruncatedClient(),
        expected_model=BATCH_A_MODEL,
        terminal_question_ids=BATCH_A_QUESTION_IDS,
        terminal_json_question_ids=BATCH_A_QUESTION_IDS,
    )
    with tempfile.TemporaryDirectory(
        dir=PROJECT_ROOT / "results" / "raw"
    ) as temporary:
        batch = execute_batch_a_validation(
            api_key="offline-q02-terminal-revision-secret",
            registry=FrozenH2MockRegistry(),
            transport=transport,
            authority=validate_offline_execution_request(
                confirmation=BATCH_A_OFFLINE_CONFIRMATION
            ),
            output_parent=Path(temporary),
            run_id="q02-terminal-truncation-saved-response-regression",
        )
        offline_audit = json.loads(
            (batch.output_dir / "transport_audit.json").read_text(
                encoding="utf-8"
            )
        )
        case = batch.cases[0]

    saved_real_state = json.loads(
        SAVED_Q02_RUN_STATE_PATH.read_text(encoding="utf-8")
    )
    real_authority = ValidatedBatchAExecutionAuthority(
        mode="real_transport",
        batch_id="A",
        question_ids=BATCH_A_QUESTION_IDS,
        model=BATCH_A_MODEL,
        response_attempt_upper_bound=BATCH_A_RESPONSE_ATTEMPT_CAP,
        automatic_retry_count=BATCH_A_AUTOMATIC_RETRIES,
    )
    real_audit_preview = _safe_transport_audit(
        transport=None,
        authority=real_authority,
        run_state=saved_real_state,
    )

    expected_states = {
        "report_traceability": NOT_EVALUATED,
        "report_completeness": NOT_EVALUATED,
        "chart_acceptance": NOT_EVALUATED,
    }
    passed = (
        direct.status == "failed"
        and direct.error_stage == "model_response"
        and direct.error_message
        == "模型终态响应达到输出上限，JSON可能不完整"
        and [call.tool_name for call in direct.tool_calls]
        == ["rank_products"]
        and len(direct.raw_responses) == 2
        and validation.status == "failed"
        and validation.tool_reference_answer_status == "passed"
        and validation.report_content_acceptance_status == NOT_EVALUATED
        and batch.summary["primary_stop_codes"]
        == ["terminal_output_truncated"]
        and "q02_chart_count_mismatch" not in case["program_failures"]
        and case["evaluation_states"] == expected_states
        and [request.max_tokens for request in transport.requests]
        == [4096, 8192]
        and offline_audit["execution_mode"]
        == "offline_injected_transport"
        and real_audit_preview["execution_mode"] == "real_transport"
        and real_audit_preview["attempted"] == 2
        and real_audit_preview["http_responses_received"] == 2
        and real_audit_preview["parsed_responses"] == 2
        and real_audit_preview["failed_attempts"] == 0
        and real_audit_preview["real_network_opened"] is True
        and real_audit_preview["real_model_response_received"] is True
        and real_audit_preview["api_key_value_saved"] is False
        and real_audit_preview["api_key_source_saved"] is False
    )
    return Q02TerminalRevisionImplementationResult(
        passed=passed,
        direct_outcome_status=direct.status,
        direct_error_stage=direct.error_stage,
        direct_error_message=direct.error_message,
        direct_tool_names=tuple(call.tool_name for call in direct.tool_calls),
        direct_response_count=len(direct.raw_responses),
        tool_reference_answer_status=validation.tool_reference_answer_status,
        report_content_acceptance_status=(
            validation.report_content_acceptance_status
        ),
        fixed_validation_issue_paths=tuple(
            item.path for item in validation.issues
        ),
        batch_primary_stop_stage=batch.summary["primary_stop_stage"],
        batch_primary_stop_codes=tuple(batch.summary["primary_stop_codes"]),
        batch_acceptance_consequences=tuple(
            batch.summary["acceptance_consequences"]
        ),
        batch_not_evaluated_checks=tuple(
            batch.summary["not_evaluated_checks"]
        ),
        batch_program_failures=tuple(case["program_failures"]),
        batch_evaluation_states=dict(case["evaluation_states"]),
        request_max_tokens=tuple(
            request.max_tokens for request in transport.requests
        ),
        offline_transport_audit=offline_audit,
        saved_real_transport_audit_preview=real_audit_preview,
        real_model_called=False,
        network_used=False,
        api_key_read=False,
    )
