"""V2.3.4.1 candidate using the six-slot section-purpose contract."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from src.agent_protocol import FinalReportResponse
from src.deepseek_client import DeepSeekChatClient, DeepSeekClientError, _default_transport
from src.deepseek_section_purpose_transport_v2_3_4_1 import DeepSeekSectionPurposeTransportV2_3_4_1
from src.online_native_tool_candidate_v2_1_revision import (
    ResponseLimitedStrictNativeClient, validate_native_real_authorization,
)
from src.online_native_tool_candidate_v2_3_4 import (
    FrozenSlotSelectingClientV2_3_4, FrozenSlotSelectionTraceV2_3_4,
    NativeToolOnlineCandidateV2_3_4, validate_report_slot_binding,
)
from src.section_purpose_contract_v2_3_4_1 import (
    SELECTION_INSTRUCTION, SectionPurposeSelectionDraftV2_3_4_1,
    SectionPurposeValidationError, build_section_purpose_catalog,
    validate_section_purpose_selection,
)


class SectionPurposeSelectingClientV2_3_4_1:
    def __init__(self, delegate: ResponseLimitedStrictNativeClient) -> None:
        self.delegate = delegate
        self.raw_responses: list[dict[str, Any]] = []
        self.selection_traces: list[FrozenSlotSelectionTraceV2_3_4] = []

    def complete_strict_tools(
        self, *, messages: list[dict[str, Any]], tools: list[dict[str, Any]],
        tool_choice: str = "auto", response_format: dict[str, str] | None = None,
    ):
        terminal = (
            tool_choice == "none" and response_format == {"type": "json_object"}
            and any(item.get("role") == "tool" for item in messages)
        )
        if not terminal:
            result = self.delegate.complete_strict_tools(
                messages=messages, tools=tools, tool_choice=tool_choice,
                response_format=response_format,
            )
            self.raw_responses.append(result.raw_response)
            return result
        source = FrozenSlotSelectingClientV2_3_4._source_envelope(messages)
        catalog = build_section_purpose_catalog(source)
        planner_messages = [
            {"role": "system", "content": SELECTION_INSTRUCTION + "\n" + json.dumps(
                SectionPurposeSelectionDraftV2_3_4_1.model_json_schema(),
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
            draft = SectionPurposeSelectionDraftV2_3_4_1.model_validate_json(response.content)
            validated = validate_section_purpose_selection(draft, catalog, source)
        except (ValueError, SectionPurposeValidationError) as exc:
            self.selection_traces.append(FrozenSlotSelectionTraceV2_3_4(
                response_index=len(self.raw_responses),
                phase="section_purpose_atom_selection",
                status="rejected_before_final_report", slot_count=0,
                selected_atom_count=0, final_report_request_sent=False,
            ))
            raise DeepSeekClientError(f"atom_selection_validation: {exc}") from exc
        self.selection_traces.append(FrozenSlotSelectionTraceV2_3_4(
            response_index=len(self.raw_responses),
            phase="section_purpose_atom_selection", status="passed",
            slot_count=6,
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
                parsed = FinalReportResponse.model_validate_json(final.content)
                validate_report_slot_binding(parsed, validated)
            except (ValueError, SectionPurposeValidationError) as exc:
                raise DeepSeekClientError(f"slot_report_binding_validation: {exc}") from exc
        return final


@dataclass
class NativeToolOnlineCandidateV2_3_4_1(NativeToolOnlineCandidateV2_3_4):
    def __post_init__(self) -> None:
        if self.transport is None:
            validate_native_real_authorization(
                confirmation=self.real_call_confirmation,
                approved_model_responses=self.response_limit,
                question_count=self.question_count,
            )
        self.terminal_transport = DeepSeekSectionPurposeTransportV2_3_4_1(
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
        self.client = SectionPurposeSelectingClientV2_3_4_1(self.response_limiter)


__all__ = ["NativeToolOnlineCandidateV2_3_4_1", "SectionPurposeSelectingClientV2_3_4_1"]
