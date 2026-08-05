"""V2.3.4.2 native-tool candidate with call isolation and arithmetic guard."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable

from src.agent_protocol import FinalReportResponse
from src.deepseek_client import DeepSeekChatClient, DeepSeekClientError, _default_transport
from src.deepseek_internal_call_isolation_transport_v2_3_4_2 import (
    DeepSeekInternalCallIsolationTransportV2_3_4_2,
    ModelVisibleCallIsolationTransportV2_3_4_2,
)
from src.native_tool_agent_v2_1_revision import RetailNativeToolAgentV2_1Revision
from src.online_native_tool_candidate_v2_1_revision import (
    ResponseLimitedStrictNativeClient,
    validate_native_real_authorization,
)
from src.online_native_tool_candidate_v2_3_1 import ALL_FIXED_QUESTION_IDS
from src.online_native_tool_candidate_v2_3_4 import (
    FrozenSlotSelectionTraceV2_3_4,
    NativeToolOnlineCandidateV2_3_4,
    validate_report_slot_binding,
)
from src.prompt_contract import load_native_tool_agent_prompts_evidence_guard_v1
from src.report_terminal_protocol_guard_v2_3_4_2 import (
    ReportTerminalProtocolGuardError,
    TerminalMappingTraceV2_3_4_2,
    build_isolated_terminal_context,
    map_model_report_to_internal_response,
    model_control_response_schema_v2_3_4_2,
    validate_model_arithmetic_intent,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _identity_terminal_context(value: Any) -> Any:
    return value


def _project_runtime_messages_v2_3_4_2(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Replace frozen model-facing Prompt/Schema without mutating old files."""
    old_prompt = load_native_tool_agent_prompts_evidence_guard_v1().report.content
    new_prompt = (
        PROJECT_ROOT
        / "prompts"
        / "native_tool_report_internal_source_v2_3_4_2.md"
    ).read_text(encoding="utf-8").strip()
    old_schema = json.dumps(
        FinalReportResponse.model_json_schema(),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    new_schema = json.dumps(
        model_control_response_schema_v2_3_4_2(),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    projected: list[dict[str, Any]] = []
    replaced = False
    for message in messages:
        copied = dict(message)
        if copied.get("role") == "system" and isinstance(
            copied.get("content"), str
        ):
            content = copied["content"]
            if old_prompt not in content or old_schema not in content:
                raise DeepSeekClientError(
                    "runtime_prompt_projection: frozen Prompt or Schema marker missing"
                )
            copied["content"] = content.replace(
                old_prompt, new_prompt, 1
            ).replace(old_schema, new_schema, 1)
            replaced = True
        projected.append(copied)
    if not replaced:
        raise DeepSeekClientError(
            "runtime_prompt_projection: system message missing"
        )
    return projected
from src.section_purpose_contract_v2_3_4_1 import (
    SELECTION_INSTRUCTION,
    SectionPurposeSelectionDraftV2_3_4_1,
    SectionPurposeValidationError,
    build_section_purpose_catalog,
    validate_section_purpose_selection,
)


class CallIsolatedSectionPurposeClientV2_3_4_2:
    def __init__(
        self,
        delegate: ResponseLimitedStrictNativeClient,
        *,
        runtime_message_projector: Callable[
            [list[dict[str, Any]]], list[dict[str, Any]]
        ] = _project_runtime_messages_v2_3_4_2,
        terminal_context_projector: Callable[[Any], Any] = (
            _identity_terminal_context
        ),
        selection_instruction_builder: Callable[[Any], str] = (
            lambda _catalog: SELECTION_INSTRUCTION
        ),
        terminal_draft_validator: Callable[[Any], list[dict[str, Any]]] = (
            lambda _response: []
        ),
        terminal_repair_limit: int = 0,
        terminal_repair_instruction: str = (
            "Return one corrected final report JSON. Change only claims needed "
            "to resolve every listed issue. Keep the six-section order and use "
            "only the same local evidence."
        ),
        terminal_protocol_error_feedback_builder: Callable[
            [str, str, str], list[dict[str, Any]]
        ] = (lambda _code, _message, _content: []),
    ) -> None:
        self.delegate = delegate
        self.runtime_message_projector = runtime_message_projector
        self.terminal_context_projector = terminal_context_projector
        self.selection_instruction_builder = selection_instruction_builder
        self.terminal_draft_validator = terminal_draft_validator
        self.terminal_repair_limit = terminal_repair_limit
        self.terminal_repair_instruction = terminal_repair_instruction
        self.terminal_protocol_error_feedback_builder = (
            terminal_protocol_error_feedback_builder
        )
        self.raw_responses: list[dict[str, Any]] = []
        self.selection_traces: list[FrozenSlotSelectionTraceV2_3_4] = []
        self.terminal_protocol_traces: list[dict[str, Any]] = []
        self.runtime_prompt_projection_count = 0

    @staticmethod
    def _source_envelope(messages: list[dict[str, Any]]):
        from src.online_native_tool_candidate_v2_3_4 import FrozenSlotSelectingClientV2_3_4

        return FrozenSlotSelectingClientV2_3_4._source_envelope(messages)

    def complete_strict_tools(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: str = "auto",
        response_format: dict[str, str] | None = None,
    ):
        terminal = (
            tool_choice == "none"
            and response_format == {"type": "json_object"}
            and any(item.get("role") == "tool" for item in messages)
        )
        if not terminal:
            projected_messages = self.runtime_message_projector(messages)
            self.runtime_prompt_projection_count += 1
            result = self.delegate.complete_strict_tools(
                messages=projected_messages,
                tools=tools,
                tool_choice=tool_choice,
                response_format=response_format,
            )
            self.raw_responses.append(result.raw_response)
            return result

        source = self._source_envelope(messages)
        catalog = build_section_purpose_catalog(source)
        planner_messages = [
            {
                "role": "system",
                "content": self.selection_instruction_builder(catalog)
                + "\n"
                + json.dumps(
                    SectionPurposeSelectionDraftV2_3_4_1.model_json_schema(),
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            },
            *[
                item
                for item in messages
                if item.get("role") == "user"
                and isinstance(item.get("content"), str)
                and not item["content"].lstrip().startswith("{")
            ],
            {"role": "user", "content": catalog.model_dump_json()},
        ]
        response = self.delegate.complete_strict_tools(
            messages=planner_messages,
            tools=tools,
            tool_choice="none",
            response_format={"type": "json_object"},
        )
        self.raw_responses.append(response.raw_response)
        try:
            if response.content is None:
                raise ValueError("selector returned no JSON content")
            draft = SectionPurposeSelectionDraftV2_3_4_1.model_validate_json(
                response.content
            )
            validated = validate_section_purpose_selection(draft, catalog, source)
        except (ValueError, SectionPurposeValidationError) as exc:
            self.selection_traces.append(
                FrozenSlotSelectionTraceV2_3_4(
                    response_index=len(self.raw_responses),
                    phase="section_purpose_atom_selection_v2_3_4_2",
                    status="rejected_before_final_report",
                    slot_count=0,
                    selected_atom_count=0,
                    final_report_request_sent=False,
                )
            )
            raise DeepSeekClientError(f"atom_selection_validation: {exc}") from exc

        context = self.terminal_context_projector(
            build_isolated_terminal_context(validated)
        )
        self.selection_traces.append(
            FrozenSlotSelectionTraceV2_3_4(
                response_index=len(self.raw_responses),
                phase="section_purpose_atom_selection_v2_3_4_2",
                status="passed",
                slot_count=6,
                selected_atom_count=sum(
                    len(item.selected_atom_ids) for item in validated.slots
                ),
                final_report_request_sent=True,
            )
        )
        final_messages = self.runtime_message_projector(messages) + [
            {"role": "user", "content": context.model_visible.model_dump_json()}
        ]
        repair_messages: list[dict[str, Any]] = []
        for repair_index in range(self.terminal_repair_limit + 1):
            final = self.delegate.complete_strict_tools(
                messages=final_messages + repair_messages,
                tools=tools,
                tool_choice="none",
                response_format={"type": "json_object"},
            )
            self.runtime_prompt_projection_count += 1
            self.raw_responses.append(final.raw_response)
            if final.content is None:
                return final
            mapped = None
            trace: TerminalMappingTraceV2_3_4_2 | None = None
            try:
                mapped, trace = map_model_report_to_internal_response(
                    content=final.content,
                    context=context,
                    trusted_validated=validated,
                )
                validate_report_slot_binding(mapped, validated)
                arithmetic_issues = validate_model_arithmetic_intent(
                    mapped.report, validated
                )
                if arithmetic_issues:
                    first = arithmetic_issues[0]
                    raise ReportTerminalProtocolGuardError(
                        first.code,
                        f"{first.location} uses unsupported arithmetic intent {first.intent}",
                    )
            except (ReportTerminalProtocolGuardError, ValueError) as exc:
                try:
                    parsed_payload = json.loads(final.content)
                except json.JSONDecodeError:
                    parsed_payload = None
                code = getattr(exc, "code", "slot_report_binding_validation")
                repair_issues = self.terminal_protocol_error_feedback_builder(
                    code, str(exc), final.content
                )
                if repair_issues and repair_index < self.terminal_repair_limit:
                    self.terminal_protocol_traces.append(
                        {
                            "status": "repair_requested",
                            "error_code": code,
                            "repair_index": repair_index + 1,
                            "validation_issues": repair_issues,
                            "parsed_model_response": parsed_payload,
                            "mapped_program_response": (
                                mapped.model_dump(mode="json")
                                if mapped is not None
                                else None
                            ),
                        }
                    )
                    feedback = {
                        "phase": "deterministic_report_validation_feedback",
                        "repair_attempt": repair_index + 1,
                        "issues": repair_issues,
                        "instruction": self.terminal_repair_instruction,
                    }
                    repair_messages = [
                        {"role": "assistant", "content": final.content},
                        {
                            "role": "user",
                            "content": json.dumps(
                                feedback,
                                ensure_ascii=False,
                                separators=(",", ":"),
                            ),
                        },
                    ]
                    continue
                self.terminal_protocol_traces.append(
                    {
                        "status": "failed_stopped",
                        "error_code": code,
                        "error_message": str(exc),
                        "parsed_model_response": parsed_payload,
                        "mapped_program_response": (
                            mapped.model_dump(mode="json")
                            if mapped is not None
                            else None
                        ),
                    }
                )
                raise DeepSeekClientError(
                    f"terminal_protocol_validation: {code}: {exc}"
                ) from exc
            issues = self.terminal_draft_validator(mapped)
            if issues:
                if repair_index >= self.terminal_repair_limit:
                    self.terminal_protocol_traces.append(
                        {
                            "status": "failed_stopped",
                            "error_code": "deterministic_report_validation_failed",
                            "validation_issues": issues,
                            "parsed_model_response": trace.parsed_model_response,
                            "mapped_program_response": trace.mapped_program_response,
                        }
                    )
                    raise DeepSeekClientError(
                        "terminal_protocol_validation: "
                        "deterministic_report_validation_failed"
                    )
                self.terminal_protocol_traces.append(
                    {
                        "status": "repair_requested",
                        "error_code": "deterministic_report_validation_failed",
                        "repair_index": repair_index + 1,
                        "validation_issues": issues,
                        "parsed_model_response": trace.parsed_model_response,
                        "mapped_program_response": trace.mapped_program_response,
                    }
                )
                feedback = {
                    "phase": "deterministic_report_validation_feedback",
                    "repair_attempt": repair_index + 1,
                    "issues": issues,
                    "instruction": self.terminal_repair_instruction,
                }
                repair_messages = [
                    {"role": "assistant", "content": final.content},
                    {
                        "role": "user",
                        "content": json.dumps(
                            feedback, ensure_ascii=False, separators=(",", ":")
                        ),
                    },
                ]
                continue
            self.terminal_protocol_traces.append(
                {
                    "status": "passed",
                    "error_code": None,
                    "parsed_model_response": trace.parsed_model_response,
                    "mapped_program_response": trace.mapped_program_response,
                    "mapped_chart_sources": list(trace.mapped_chart_sources),
                }
            )
            return replace(final, content=mapped.model_dump_json())
        raise AssertionError("terminal repair loop exhausted unexpectedly")


@dataclass
class NativeToolOnlineCandidateV2_3_4_2(NativeToolOnlineCandidateV2_3_4):
    runtime_message_projector: Callable[
        [list[dict[str, Any]]], list[dict[str, Any]]
    ] = field(
        init=False,
        default_factory=lambda: _project_runtime_messages_v2_3_4_2,
        repr=False,
    )
    terminal_protocol_trace: tuple[dict[str, Any], ...] = field(
        init=False, default=()
    )
    terminal_context_projector: Callable[[Any], Any] = field(
        init=False,
        default_factory=lambda: _identity_terminal_context,
        repr=False,
    )
    selection_instruction_builder: Callable[[Any], str] = field(
        init=False,
        default_factory=lambda: (lambda _catalog: SELECTION_INSTRUCTION),
        repr=False,
    )
    terminal_draft_validator: Callable[[Any], list[dict[str, Any]]] = field(
        init=False,
        default_factory=lambda: (lambda _response: []),
        repr=False,
    )
    terminal_repair_limit: int = field(init=False, default=0, repr=False)
    terminal_repair_instruction: str = field(
        init=False,
        default=(
            "Return one corrected final report JSON. Change only claims needed "
            "to resolve every listed issue. Keep the six-section order and use "
            "only the same local evidence."
        ),
        repr=False,
    )
    terminal_protocol_error_feedback_builder: Callable[
        [str, str, str], list[dict[str, Any]]
    ] = field(
        init=False,
        default_factory=lambda: (lambda _code, _message, _content: []),
        repr=False,
    )
    real_authorization_validator: Callable[..., None] = field(
        init=False,
        default_factory=lambda: validate_native_real_authorization,
        repr=False,
    )

    def __post_init__(self) -> None:
        if self.transport is None:
            self.real_authorization_validator(
                confirmation=self.real_call_confirmation,
                approved_model_responses=self.response_limit,
                question_count=self.question_count,
            )
        self.visibility_transport = ModelVisibleCallIsolationTransportV2_3_4_2(
            delegate=self.transport or _default_transport
        )
        self.terminal_transport = DeepSeekInternalCallIsolationTransportV2_3_4_2(
            delegate=self.visibility_transport
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
        self.client = CallIsolatedSectionPurposeClientV2_3_4_2(
            self.response_limiter,
            runtime_message_projector=self.runtime_message_projector,
            terminal_context_projector=self.terminal_context_projector,
            selection_instruction_builder=self.selection_instruction_builder,
            terminal_draft_validator=self.terminal_draft_validator,
            terminal_repair_limit=self.terminal_repair_limit,
            terminal_repair_instruction=self.terminal_repair_instruction,
            terminal_protocol_error_feedback_builder=(
                self.terminal_protocol_error_feedback_builder
            ),
        )

    def run_turn(
        self, *, session_id: str, turn_id: str, question: str, result_root: str
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
        if len(self.client.raw_responses) > len(outcome.raw_responses):
            outcome = replace(
                outcome,
                model_response_count=len(self.client.raw_responses),
                raw_responses=tuple(self.client.raw_responses),
            )
        if (
            outcome.status == "failed"
            and outcome.error_stage == "model_response"
            and (outcome.error_message or "").startswith(
                "atom_selection_validation:"
            )
        ):
            outcome = replace(outcome, error_stage="atom_selection_validation")
        if (
            outcome.status == "failed"
            and outcome.error_stage == "model_response"
            and (outcome.error_message or "").startswith(
                "terminal_protocol_validation:"
            )
        ):
            outcome = replace(
                outcome, error_stage="terminal_protocol_validation"
            )
        self.last_trace = tuple(
            replace(item, visible_tool_names=())
            if item.requested_tool_choice == "none"
            else item
            for item in agent.last_trace
        )
        self.atom_selection_trace = tuple(self.client.selection_traces)
        self.terminal_protocol_trace = tuple(
            self.client.terminal_protocol_traces
        )
        return outcome

    def transport_audit_payload(self) -> dict[str, Any]:
        payload = self.terminal_transport.audit_payload()
        payload["model_visibility"] = self.visibility_transport.audit_payload()
        payload["terminal_protocol_trace_count"] = len(
            self.client.terminal_protocol_traces
        )
        payload["runtime_prompt_projection_count"] = (
            self.client.runtime_prompt_projection_count
        )
        payload["formal_report_schema_changed"] = False
        payload["fact_schema_changed"] = False
        payload["post_hoc_report_prose_repair"] = False
        return payload


__all__ = [
    "CallIsolatedSectionPurposeClientV2_3_4_2",
    "NativeToolOnlineCandidateV2_3_4_2",
]
