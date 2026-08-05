"""V2.3.2 candidate using claim-local evidence planning bundles."""

from __future__ import annotations

from dataclasses import dataclass

from src.deepseek_client import DeepSeekChatClient, _default_transport
from src.deepseek_report_terminal_transport_v2_3_2 import (
    DeepSeekReportTerminalTransportV2_3_2,
)
from src.online_native_tool_candidate_v2_1_revision import (
    ResponseLimitedStrictNativeClient,
    validate_native_real_authorization,
)
from src.online_native_tool_candidate_v2_3_1 import (
    ALL_FIXED_QUESTION_IDS,
    NATIVE_REAL_MODEL_CONFIRMATION,
    NativeToolOnlineCandidateV2_3_1,
)


@dataclass
class NativeToolOnlineCandidateV2_3_2(NativeToolOnlineCandidateV2_3_1):
    """Change only the report-terminal planning representation."""

    def __post_init__(self) -> None:
        if self.transport is None:
            validate_native_real_authorization(
                confirmation=self.real_call_confirmation,
                approved_model_responses=self.response_limit,
                question_count=self.question_count,
            )
        base_transport = self.transport or _default_transport
        self.terminal_transport = DeepSeekReportTerminalTransportV2_3_2(
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


__all__ = [
    "ALL_FIXED_QUESTION_IDS",
    "NATIVE_REAL_MODEL_CONFIRMATION",
    "NativeToolOnlineCandidateV2_3_2",
]
