"""Safety-wrapped online candidate for the corrected native-tool mainline."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

from src.deepseek_client import (
    ChatCompletionResult,
    DEEPSEEK_MODEL,
    DeepSeekChatClient,
    DeepSeekClientError,
    HttpTransport,
    strict_tool_request_max_tokens,
)
from src.native_tool_agent_v2_1_revision import (
    NativeModelStepTrace,
    NativeToolRegistry,
    RetailNativeToolAgentV2_1Revision,
)


NATIVE_REAL_MODEL_CONFIRMATION = (
    "I_AUTHORIZE_NATIVE_TOOL_V2_1_REVISION_REAL_MODEL_CALLS"
)
MAX_RESPONSES_PER_FIXED_QUESTION = 4


@dataclass(frozen=True)
class NativeResponseLimitSnapshot:
    limit: int
    attempted: int
    completed: int
    failed: int


class ResponseLimitedStrictNativeClient:
    """Reserve a response attempt before the HTTP transport is entered."""

    def __init__(
        self,
        client: DeepSeekChatClient,
        *,
        limit: int,
        response_event_sink: Any | None = None,
        batch_timeout_seconds: float | None = None,
        started_monotonic: float | None = None,
    ) -> None:
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError("native model response limit must be an integer")
        if limit <= 0:
            raise ValueError("native model response limit must be positive")
        self.client = client
        self.limit = limit
        self.attempted = 0
        self.completed = 0
        self.failed = 0
        self.response_event_sink = response_event_sink
        self.batch_timeout_seconds = batch_timeout_seconds
        self.started_monotonic = (
            perf_counter()
            if started_monotonic is None
            else started_monotonic
        )
        if batch_timeout_seconds is not None and batch_timeout_seconds <= 0:
            raise ValueError("batch timeout must be positive")
        if response_event_sink is not None:
            self.client.response_event_sink = self._forward_client_event

    def _emit(self, event_type: str, payload: dict[str, Any]) -> None:
        if self.response_event_sink is not None:
            self.response_event_sink(event_type, payload)

    def _forward_client_event(
        self, event_type: str, payload: dict[str, Any]
    ) -> None:
        self._emit(
            event_type,
            {"attempt_index": self.attempted, **payload},
        )

    def complete_strict_tools(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: str = "auto",
        response_format: dict[str, str] | None = None,
    ) -> ChatCompletionResult:
        if self.attempted >= self.limit:
            raise DeepSeekClientError(
                "native model response limit reached before transport"
            )
        remaining: float | None = None
        if self.batch_timeout_seconds is not None:
            elapsed = perf_counter() - self.started_monotonic
            remaining = self.batch_timeout_seconds - elapsed
            if remaining <= 0:
                self._emit(
                    "batch_deadline_reached",
                    {
                        "elapsed_seconds": round(elapsed, 6),
                        "batch_timeout_seconds": self.batch_timeout_seconds,
                        "attempted": self.attempted,
                    },
                )
                raise DeepSeekClientError(
                    "batch deadline reached before response attempt"
                )
        self.attempted += 1
        original_timeout = float(
            getattr(self.client, "timeout_seconds", 120.0)
        )
        effective_timeout = (
            original_timeout
            if remaining is None
            else min(original_timeout, max(0.001, remaining))
        )
        self._emit(
            "attempt_reserved",
            {
                "attempt_index": self.attempted,
                "remaining_batch_seconds": (
                    None if remaining is None else round(remaining, 6)
                ),
                "effective_request_timeout_seconds": round(
                    effective_timeout, 6
                ),
            },
        )
        if hasattr(self.client, "timeout_seconds"):
            self.client.timeout_seconds = effective_timeout
        try:
            max_tokens = strict_tool_request_max_tokens(
                messages=messages,
                tool_choice=tool_choice,
                response_format=response_format,
            )
            result = self.client.complete_strict_tools(
                messages=messages,
                tools=tools,
                tool_choice=tool_choice,
                response_format=response_format,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            self.failed += 1
            self._emit(
                "attempt_failed",
                {
                    "attempt_index": self.attempted,
                    "exception_type": type(exc).__name__,
                    "message": str(exc),
                },
            )
            raise
        finally:
            if hasattr(self.client, "timeout_seconds"):
                self.client.timeout_seconds = original_timeout
        self.completed += 1
        self._emit(
            "response_parsed",
            {
                "attempt_index": self.attempted,
                "raw_response": result.raw_response,
            },
        )
        return result

    def snapshot(self) -> NativeResponseLimitSnapshot:
        return NativeResponseLimitSnapshot(
            limit=self.limit,
            attempted=self.attempted,
            completed=self.completed,
            failed=self.failed,
        )


def validate_native_real_authorization(
    *,
    confirmation: str,
    approved_model_responses: int,
    question_count: int,
) -> None:
    if confirmation != NATIVE_REAL_MODEL_CONFIRMATION:
        raise ValueError("native real-model confirmation is missing")
    if (
        isinstance(approved_model_responses, bool)
        or not isinstance(approved_model_responses, int)
        or approved_model_responses <= 0
    ):
        raise ValueError("approved model responses must be a positive integer")
    if (
        isinstance(question_count, bool)
        or not isinstance(question_count, int)
        or question_count <= 0
    ):
        raise ValueError("question count must be a positive integer")
    if approved_model_responses > (
        question_count * MAX_RESPONSES_PER_FIXED_QUESTION
    ):
        raise ValueError("approved model response limit is too broad")


@dataclass
class NativeToolOnlineCandidateV2_1Revision:
    """Run the native orchestrator through the real client boundary.

    Supplying an injected transport is offline mode.  A missing transport is
    rejected unless the caller separately supplies the exact real-call
    confirmation and a bounded question count.
    """

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
    q06_terminal_lock_enabled: bool = True
    q06_terminal_json_enabled: bool = True
    terminal_lock_question_ids: tuple[str, ...] | None = None
    terminal_json_question_ids: tuple[str, ...] | None = None
    last_trace: tuple[NativeModelStepTrace, ...] = field(
        init=False,
        default=(),
    )
    client: ResponseLimitedStrictNativeClient = field(
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
        client_arguments: dict[str, Any] = {
            "api_key": self.api_key,
            "model": self.model,
            "timeout_seconds": self.request_timeout_seconds,
        }
        if self.transport is not None:
            client_arguments["transport"] = self.transport
        deepseek = DeepSeekChatClient(**client_arguments)
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
        result_root: str = "results/raw/native_tool_online_candidate",
    ) -> Any:
        agent = RetailNativeToolAgentV2_1Revision(
            client=self.client,
            registry=self.registry,
            q06_terminal_lock_enabled=self.q06_terminal_lock_enabled,
            q06_terminal_json_enabled=self.q06_terminal_json_enabled,
            terminal_lock_question_ids=self.terminal_lock_question_ids,
            terminal_json_question_ids=self.terminal_json_question_ids,
        )
        outcome = agent.run_turn(
            session_id=session_id,
            turn_id=turn_id,
            question=question,
            result_root=result_root,
        )
        self.last_trace = agent.last_trace
        return outcome

    def response_limit_snapshot(self) -> NativeResponseLimitSnapshot:
        return self.client.snapshot()
