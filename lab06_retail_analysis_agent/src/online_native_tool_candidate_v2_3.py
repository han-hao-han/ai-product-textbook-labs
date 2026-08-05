"""Online/offline candidate using the V2.3 terminal transport boundary."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from time import perf_counter
from typing import Any

from src.deepseek_client import (
    DEEPSEEK_MODEL,
    DeepSeekChatClient,
    HttpTransport,
    _default_transport,
)
from src.deepseek_report_terminal_transport_v2_3 import (
    DeepSeekReportTerminalTransportV2_3,
)
from src.native_tool_agent_v2_1_revision import (
    FIXED_TOOL_SEQUENCES,
    NativeModelStepTrace,
    NativeToolRegistry,
    RetailNativeToolAgentV2_1Revision,
)
from src.online_native_tool_candidate_v2_1_revision import (
    NATIVE_REAL_MODEL_CONFIRMATION,
    ResponseLimitedStrictNativeClient,
    validate_native_real_authorization,
)


ALL_FIXED_QUESTION_IDS = tuple(FIXED_TOOL_SEQUENCES)


@dataclass
class NativeToolOnlineCandidateV2_3:
    """Preserve native tool selection and switch only terminal transport."""

    api_key: str = field(repr=False)
    registry: NativeToolRegistry
    response_limit: int
    model: str = DEEPSEEK_MODEL
    transport: HttpTransport | None = field(default=None, repr=False)
    real_call_confirmation: str = field(default="", repr=False)
    question_count: int = 1
    request_timeout_seconds: float = 120.0
    batch_timeout_seconds: float | None = None
    batch_started_monotonic: float | None = None
    response_event_sink: Any | None = field(default=None, repr=False)
    terminal_question_ids: tuple[str, ...] = ALL_FIXED_QUESTION_IDS
    last_trace: tuple[NativeModelStepTrace, ...] = field(
        init=False,
        default=(),
    )
    client: ResponseLimitedStrictNativeClient = field(
        init=False,
        repr=False,
    )
    terminal_transport: DeepSeekReportTerminalTransportV2_3 = field(
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        if self.transport is None:
            validate_native_real_authorization(
                confirmation=self.real_call_confirmation,
                approved_model_responses=self.response_limit,
                question_count=self.question_count,
            )
        base_transport = self.transport or _default_transport
        self.terminal_transport = DeepSeekReportTerminalTransportV2_3(
            delegate=base_transport
        )
        deepseek = DeepSeekChatClient(
            api_key=self.api_key,
            model=self.model,
            timeout_seconds=self.request_timeout_seconds,
            transport=self.terminal_transport,
        )
        self.client = ResponseLimitedStrictNativeClient(
            deepseek,
            limit=self.response_limit,
            response_event_sink=self.response_event_sink,
            batch_timeout_seconds=self.batch_timeout_seconds,
            started_monotonic=self.batch_started_monotonic,
        )

    def run_turn(
        self,
        *,
        session_id: str,
        turn_id: str,
        question: str,
        result_root: str = "results/raw/native_tool_online_candidate_v2_3",
    ) -> Any:
        agent = RetailNativeToolAgentV2_1Revision(
            client=self.client,
            registry=self.registry,
            terminal_lock_question_ids=self.terminal_question_ids,
            terminal_json_question_ids=self.terminal_question_ids,
        )
        outcome = agent.run_turn(
            session_id=session_id,
            turn_id=turn_id,
            question=question,
            result_root=result_root,
        )
        self.last_trace = tuple(
            replace(step, visible_tool_names=())
            if (
                step.requested_tool_choice == "none"
                and step.requested_response_format == {"type": "json_object"}
            )
            else step
            for step in agent.last_trace
        )
        return outcome

    def response_limit_snapshot(self) -> Any:
        return self.client.snapshot()

    def transport_audit_payload(self) -> dict[str, Any]:
        return self.terminal_transport.audit_payload()


__all__ = [
    "ALL_FIXED_QUESTION_IDS",
    "NATIVE_REAL_MODEL_CONFIRMATION",
    "NativeToolOnlineCandidateV2_3",
]
