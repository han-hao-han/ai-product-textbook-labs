"""V2.3.4 native-tool candidate with counted atom-selection response."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from typing import Any

from src.claim_evidence_bundles_v2_3_2 import ClaimEvidenceEnvelopeV2_3_2
from src.agent_protocol import FinalReportResponse
from src.deepseek_client import (
    DEEPSEEK_MODEL, ChatCompletionResult, DeepSeekChatClient, DeepSeekClientError,
    HttpTransport, _default_transport,
)
from src.deepseek_frozen_six_slot_transport_v2_3_4 import DeepSeekFrozenSixSlotTransportV2_3_4
from src.deepseek_report_terminal_transport_v2_3_2 import DeepSeekReportTerminalTransportV2_3_2
from src.frozen_six_slot_atom_selection_v2_3_4 import (
    FrozenSlotAtomSelectionDraftV2_3_4,
    FrozenSlotSelectionValidationError,
    SELECTION_INSTRUCTION,
    build_frozen_slot_catalog,
    validate_frozen_slot_selection,
)
from src.native_tool_agent_v2_1_revision import (
    NativeModelStepTrace, NativeToolRegistry, RetailNativeToolAgentV2_1Revision,
)
from src.online_native_tool_candidate_v2_1_revision import (
    NATIVE_REAL_MODEL_CONFIRMATION, NativeResponseLimitSnapshot,
    ResponseLimitedStrictNativeClient, validate_native_real_authorization,
)
from src.online_native_tool_candidate_v2_3_1 import ALL_FIXED_QUESTION_IDS


@dataclass(frozen=True)
class FrozenSlotSelectionTraceV2_3_4:
    response_index: int
    phase: str
    status: str
    slot_count: int
    selected_atom_count: int
    final_report_request_sent: bool


def _evidence_id(item: Any) -> str:
    return item.fact_id if item.evidence_type == "FACT" else (
        item.request_id if item.evidence_type == "REQUEST" else item.policy_id
    )


def validate_report_slot_binding(
    report: FinalReportResponse,
    validated: Any,
) -> None:
    """Reject cross-slot evidence borrowing before the formal report validator."""

    if re.search(r"\bCALL-\d+\b", report.report.title):
        raise FrozenSlotSelectionValidationError("call_id is forbidden in report title")
    if len(report.report.sections) != len(validated.slots):
        raise FrozenSlotSelectionValidationError("report section count differs from frozen slots")
    for section, slot in zip(report.report.sections, validated.slots):
        if section.name != slot.section_name:
            raise FrozenSlotSelectionValidationError("report section order differs from frozen slots")
        allowed = {_evidence_id(item) for item in slot.allowed_evidence}
        for claim in section.claims:
            if re.search(r"\bCALL-\d+\b", claim.statement):
                raise FrozenSlotSelectionValidationError("call_id is forbidden in report prose")
            actual = {_evidence_id(item) for item in claim.evidence}
            if not actual.issubset(allowed):
                raise FrozenSlotSelectionValidationError(
                    f"{slot.slot_id} report section borrowed evidence from another slot"
                )
    allowed_calls = {item.call_id for item in validated.allowed_chart_sources}
    if any(item.call_id not in allowed_calls for item in report.chart_requests):
        raise FrozenSlotSelectionValidationError("chart request references an unauthorized call")


class FrozenSlotSelectingClientV2_3_4:
    def __init__(self, delegate: ResponseLimitedStrictNativeClient) -> None:
        self.delegate = delegate
        self.raw_responses: list[dict[str, Any]] = []
        self.selection_traces: list[FrozenSlotSelectionTraceV2_3_4] = []

    @staticmethod
    def _source_envelope(messages: list[dict[str, Any]]) -> ClaimEvidenceEnvelopeV2_3_2:
        projected, _, _, _, added = DeepSeekReportTerminalTransportV2_3_2._project_terminal_messages(messages)
        if not added:
            raise DeepSeekClientError("V2.3.4 selection requires current-turn tool evidence")
        try:
            return ClaimEvidenceEnvelopeV2_3_2.model_validate_json(projected[-1]["content"])
        except (KeyError, ValueError) as exc:
            raise DeepSeekClientError("V2.3.4 source evidence envelope is invalid") from exc

    def complete_strict_tools(
        self, *, messages: list[dict[str, Any]], tools: list[dict[str, Any]],
        tool_choice: str = "auto", response_format: dict[str, str] | None = None,
    ) -> ChatCompletionResult:
        terminal = (
            tool_choice == "none"
            and response_format == {"type": "json_object"}
            and any(item.get("role") == "tool" for item in messages)
        )
        if not terminal:
            result = self.delegate.complete_strict_tools(
                messages=messages, tools=tools, tool_choice=tool_choice,
                response_format=response_format,
            )
            self.raw_responses.append(result.raw_response)
            return result

        source = self._source_envelope(messages)
        catalog = build_frozen_slot_catalog(source)
        planner_messages = [
            {"role": "system", "content": SELECTION_INSTRUCTION + "\n" + json.dumps(
                FrozenSlotAtomSelectionDraftV2_3_4.model_json_schema(),
                ensure_ascii=False, separators=(",", ":"),
            )},
            *[
                item for item in messages
                if item.get("role") == "user" and isinstance(item.get("content"), str)
                and not item["content"].lstrip().startswith("{")
            ],
            {"role": "user", "content": catalog.model_dump_json()},
        ]
        response = self.delegate.complete_strict_tools(
            messages=planner_messages, tools=tools, tool_choice="none",
            response_format={"type": "json_object"},
        )
        self.raw_responses.append(response.raw_response)
        try:
            if response.content is None:
                raise ValueError("selector returned no JSON content")
            draft = FrozenSlotAtomSelectionDraftV2_3_4.model_validate_json(response.content)
            validated = validate_frozen_slot_selection(draft, catalog, source)
        except (ValueError, FrozenSlotSelectionValidationError) as exc:
            self.selection_traces.append(FrozenSlotSelectionTraceV2_3_4(
                response_index=len(self.raw_responses), phase="frozen_six_slot_atom_selection",
                status="rejected_before_final_report", slot_count=0,
                selected_atom_count=0, final_report_request_sent=False,
            ))
            raise DeepSeekClientError(f"atom_selection_validation: {exc}") from exc
        self.selection_traces.append(FrozenSlotSelectionTraceV2_3_4(
            response_index=len(self.raw_responses), phase="frozen_six_slot_atom_selection",
            status="passed", slot_count=len(validated.slots),
            selected_atom_count=sum(len(item.selected_atom_ids) for item in validated.slots),
            final_report_request_sent=True,
        ))
        final = self.delegate.complete_strict_tools(
            messages=list(messages) + [{"role": "user", "content": validated.model_dump_json()}],
            tools=tools, tool_choice="none", response_format={"type": "json_object"},
        )
        self.raw_responses.append(final.raw_response)
        if final.content is not None:
            try:
                parsed_report = FinalReportResponse.model_validate_json(final.content)
                validate_report_slot_binding(parsed_report, validated)
            except (ValueError, FrozenSlotSelectionValidationError) as exc:
                raise DeepSeekClientError(f"slot_report_binding_validation: {exc}") from exc
        return final


@dataclass
class NativeToolOnlineCandidateV2_3_4:
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
    atom_selection_trace: tuple[FrozenSlotSelectionTraceV2_3_4, ...] = field(init=False, default=())

    def __post_init__(self) -> None:
        if self.transport is None:
            validate_native_real_authorization(
                confirmation=self.real_call_confirmation,
                approved_model_responses=self.response_limit,
                question_count=self.question_count,
            )
        self.terminal_transport = DeepSeekFrozenSixSlotTransportV2_3_4(
            delegate=self.transport or _default_transport
        )
        deepseek = DeepSeekChatClient(
            api_key=self.api_key, model=self.model,
            timeout_seconds=self.request_timeout_seconds,
            transport=self.terminal_transport,
        )
        self.response_limiter = ResponseLimitedStrictNativeClient(
            deepseek, limit=self.response_limit,
            response_event_sink=self.response_event_sink,
            batch_timeout_seconds=self.batch_timeout_seconds,
            started_monotonic=self.batch_started_monotonic,
        )
        self.client = FrozenSlotSelectingClientV2_3_4(self.response_limiter)

    def run_turn(self, *, session_id: str, turn_id: str, question: str, result_root: str) -> Any:
        agent = RetailNativeToolAgentV2_1Revision(
            client=self.client, registry=self.registry,
            terminal_lock_question_ids=self.terminal_question_ids,
            terminal_json_question_ids=self.terminal_question_ids,
        )
        outcome = agent.run_turn(
            session_id=session_id, turn_id=turn_id, question=question,
            result_root=result_root,
        )
        if len(self.client.raw_responses) > len(outcome.raw_responses):
            outcome = replace(
                outcome, model_response_count=len(self.client.raw_responses),
                raw_responses=tuple(self.client.raw_responses),
            )
        if (
            outcome.status == "failed" and outcome.error_stage == "model_response"
            and (outcome.error_message or "").startswith("atom_selection_validation:")
        ):
            outcome = replace(outcome, error_stage="atom_selection_validation")
        if (
            outcome.status == "failed" and outcome.error_stage == "model_response"
            and (outcome.error_message or "").startswith("slot_report_binding_validation:")
        ):
            outcome = replace(outcome, error_stage="slot_report_binding_validation")
        self.last_trace = tuple(
            replace(item, visible_tool_names=()) if item.requested_tool_choice == "none" else item
            for item in agent.last_trace
        )
        self.atom_selection_trace = tuple(self.client.selection_traces)
        return outcome

    def response_limit_snapshot(self) -> NativeResponseLimitSnapshot:
        return self.response_limiter.snapshot()

    def transport_audit_payload(self) -> dict[str, Any]:
        return self.terminal_transport.audit_payload()


__all__ = [
    "FrozenSlotSelectingClientV2_3_4", "FrozenSlotSelectionTraceV2_3_4",
    "NativeToolOnlineCandidateV2_3_4", "NATIVE_REAL_MODEL_CONFIRMATION",
    "validate_report_slot_binding",
]
