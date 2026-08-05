"""V2.3.3 native-tool candidate with a counted controlled-plan response."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from typing import Any

from src.claim_evidence_bundles_v2_3_2 import ClaimEvidenceEnvelopeV2_3_2
from src.controlled_claim_plan_v2_3_3 import (
    ClaimPlanDraftV2_3_3,
    ClaimPlanValidationError,
    PLANNER_INSTRUCTION,
    validate_claim_plan,
)
from src.deepseek_client import (
    DEEPSEEK_MODEL,
    ChatCompletionResult,
    DeepSeekChatClient,
    DeepSeekClientError,
    HttpTransport,
    _default_transport,
)
from src.deepseek_controlled_claim_plan_transport_v2_3_3 import (
    DeepSeekControlledClaimPlanTransportV2_3_3,
)
from src.deepseek_report_terminal_transport_v2_3_2 import (
    DeepSeekReportTerminalTransportV2_3_2,
)
from src.native_tool_agent_v2_1_revision import (
    NativeModelStepTrace,
    NativeToolRegistry,
    RetailNativeToolAgentV2_1Revision,
)
from src.online_native_tool_candidate_v2_1_revision import (
    NATIVE_REAL_MODEL_CONFIRMATION,
    NativeResponseLimitSnapshot,
    ResponseLimitedStrictNativeClient,
    validate_native_real_authorization,
)
from src.online_native_tool_candidate_v2_3_1 import ALL_FIXED_QUESTION_IDS


@dataclass(frozen=True)
class ClaimPlanModelTraceV2_3_3:
    response_index: int
    phase: str
    status: str
    slot_count: int
    final_report_request_sent: bool


class ControlledClaimPlanningClientV2_3_3:
    def __init__(self, delegate: ResponseLimitedStrictNativeClient) -> None:
        self.delegate = delegate
        self.raw_responses: list[dict[str, Any]] = []
        self.plan_traces: list[ClaimPlanModelTraceV2_3_3] = []

    @staticmethod
    def _source_envelope(messages: list[dict[str, Any]]) -> ClaimEvidenceEnvelopeV2_3_2:
        projected, _, _, _, added = (
            DeepSeekReportTerminalTransportV2_3_2._project_terminal_messages(messages)
        )
        if not added:
            raise DeepSeekClientError("V2.3.3 planning requires current-turn tool evidence")
        try:
            return ClaimEvidenceEnvelopeV2_3_2.model_validate_json(
                projected[-1]["content"]
            )
        except (KeyError, ValueError) as exc:
            raise DeepSeekClientError("V2.3.3 source evidence envelope is invalid") from exc

    def complete_strict_tools(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: str = "auto",
        response_format: dict[str, str] | None = None,
    ) -> ChatCompletionResult:
        terminal_with_evidence = (
            tool_choice == "none"
            and response_format == {"type": "json_object"}
            and any(item.get("role") == "tool" for item in messages)
        )
        if not terminal_with_evidence:
            result = self.delegate.complete_strict_tools(
                messages=messages,
                tools=tools,
                tool_choice=tool_choice,
                response_format=response_format,
            )
            self.raw_responses.append(result.raw_response)
            return result

        source = self._source_envelope(messages)
        planner_system = {
            "role": "system",
            "content": PLANNER_INSTRUCTION + "\n" + json.dumps(
                ClaimPlanDraftV2_3_3.model_json_schema(),
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        }
        planner_messages = [planner_system] + [
            item for item in messages if item.get("role") != "system"
        ]
        planner_response = self.delegate.complete_strict_tools(
            messages=planner_messages,
            tools=tools,
            tool_choice="none",
            response_format={"type": "json_object"},
        )
        self.raw_responses.append(planner_response.raw_response)
        if planner_response.content is None:
            raise DeepSeekClientError("claim_plan_validation: planner returned no JSON content")
        try:
            draft = ClaimPlanDraftV2_3_3.model_validate_json(planner_response.content)
            validated = validate_claim_plan(draft, source)
        except (ValueError, ClaimPlanValidationError) as exc:
            self.plan_traces.append(
                ClaimPlanModelTraceV2_3_3(
                    response_index=len(self.raw_responses),
                    phase="controlled_claim_plan",
                    status="rejected_before_final_report",
                    slot_count=0,
                    final_report_request_sent=False,
                )
            )
            raise DeepSeekClientError(f"claim_plan_validation: {exc}") from exc
        self.plan_traces.append(
            ClaimPlanModelTraceV2_3_3(
                response_index=len(self.raw_responses),
                phase="controlled_claim_plan",
                status="passed",
                slot_count=len(validated.slots),
                final_report_request_sent=True,
            )
        )
        final_messages = list(messages) + [
            {"role": "user", "content": validated.model_dump_json()}
        ]
        final_response = self.delegate.complete_strict_tools(
            messages=final_messages,
            tools=tools,
            tool_choice="none",
            response_format={"type": "json_object"},
        )
        self.raw_responses.append(final_response.raw_response)
        return final_response


@dataclass
class NativeToolOnlineCandidateV2_3_3:
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
    last_trace: tuple[NativeModelStepTrace, ...] = field(init=False, default=())
    claim_plan_trace: tuple[ClaimPlanModelTraceV2_3_3, ...] = field(init=False, default=())

    def __post_init__(self) -> None:
        if self.transport is None:
            validate_native_real_authorization(
                confirmation=self.real_call_confirmation,
                approved_model_responses=self.response_limit,
                question_count=self.question_count,
            )
        self.terminal_transport = DeepSeekControlledClaimPlanTransportV2_3_3(
            delegate=self.transport or _default_transport
        )
        deepseek = DeepSeekChatClient(
            api_key=self.api_key,
            model=self.model,
            timeout_seconds=self.request_timeout_seconds,
            transport=self.terminal_transport,
        )
        self.response_limiter = ResponseLimitedStrictNativeClient(
            deepseek,
            limit=self.response_limit,
            response_event_sink=self.response_event_sink,
            batch_timeout_seconds=self.batch_timeout_seconds,
            started_monotonic=self.batch_started_monotonic,
        )
        self.client = ControlledClaimPlanningClientV2_3_3(self.response_limiter)

    def run_turn(self, *, session_id: str, turn_id: str, question: str, result_root: str) -> Any:
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
        if len(self.client.raw_responses) > len(outcome.raw_responses):
            outcome = replace(
                outcome,
                model_response_count=len(self.client.raw_responses),
                raw_responses=tuple(self.client.raw_responses),
            )
        if (
            outcome.status == "failed"
            and outcome.error_stage == "model_response"
            and (outcome.error_message or "").startswith("claim_plan_validation:")
        ):
            outcome = replace(outcome, error_stage="claim_plan_validation")
        self.last_trace = tuple(
            replace(item, visible_tool_names=())
            if item.requested_tool_choice == "none"
            else item
            for item in agent.last_trace
        )
        self.claim_plan_trace = tuple(self.client.plan_traces)
        return outcome

    def response_limit_snapshot(self) -> NativeResponseLimitSnapshot:
        return self.response_limiter.snapshot()

    def transport_audit_payload(self) -> dict[str, Any]:
        return self.terminal_transport.audit_payload()


__all__ = [
    "ClaimPlanModelTraceV2_3_3",
    "ControlledClaimPlanningClientV2_3_3",
    "NativeToolOnlineCandidateV2_3_3",
    "NATIVE_REAL_MODEL_CONFIRMATION",
]
