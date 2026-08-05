"""Native-tool candidate using the V3 claim-level report controller."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable

from src.claim_level_report_controller_v3 import (
    ClaimControllerValidationError,
    ClaimStatementResponseV3,
    assemble_final_report_v3,
    build_claim_controller_context_v3,
)
from src.deepseek_client import DeepSeekClientError
from src.online_native_tool_candidate_combined_v11 import (
    NativeToolOnlineCandidateCombinedV11,
)
from src.online_native_tool_candidate_v2_3_4_2 import (
    CallIsolatedSectionPurposeClientV2_3_4_2,
)
from src.online_native_tool_candidate_v2_3_4 import FrozenSlotSelectionTraceV2_3_4
from src.report_terminal_protocol_guard_v2_3_4_2 import build_isolated_terminal_context
from src.section_purpose_contract_v2_3_4_1 import (
    SectionPurposeSelectionDraftV2_3_4_1,
    SectionPurposeValidationError,
    build_section_purpose_catalog,
    validate_section_purpose_selection,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROMPT_PATH = PROJECT_ROOT / "prompts" / "native_tool_claim_statement_controller_v3.md"
COMBINED_PROMPT_VERSION = (
    "1.5.6-h3-native-tool-routing-v3-atom-required-v11-claim-controller-v3"
)
MAX_RESPONSES_PER_FIXED_QUESTION_V3 = 5


def validate_claim_controller_real_authorization(
    *, confirmation: str, approved_model_responses: int, question_count: int
) -> None:
    from src.online_native_tool_candidate_v2_1_revision import NATIVE_REAL_MODEL_CONFIRMATION

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
    if approved_model_responses > question_count * MAX_RESPONSES_PER_FIXED_QUESTION_V3:
        raise ValueError("approved V3 model response limit is too broad")


class ClaimLevelTerminalClientV3(CallIsolatedSectionPurposeClientV2_3_4_2):
    """Keep native routing/atom selection, replace only final report authorship."""

    def __init__(self, *args: Any, claim_repair_limit: int = 1, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.claim_repair_limit = claim_repair_limit
        self.prompt = PROMPT_PATH.read_text(encoding="utf-8").strip()

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
            return super().complete_strict_tools(
                messages=messages,
                tools=tools,
                tool_choice=tool_choice,
                response_format=response_format,
            )

        source = self._source_envelope(messages)
        catalog = build_section_purpose_catalog(source)
        original_questions = [
            item
            for item in messages
            if item.get("role") == "user"
            and isinstance(item.get("content"), str)
            and not item["content"].lstrip().startswith("{")
        ]
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
            *original_questions,
            {"role": "user", "content": catalog.model_dump_json()},
        ]
        selection_response = self.delegate.complete_strict_tools(
            messages=planner_messages,
            tools=tools,
            tool_choice="none",
            response_format={"type": "json_object"},
        )
        self.raw_responses.append(selection_response.raw_response)
        try:
            if selection_response.content is None:
                raise ValueError("selector returned no JSON content")
            draft = SectionPurposeSelectionDraftV2_3_4_1.model_validate_json(
                selection_response.content
            )
            validated = validate_section_purpose_selection(draft, catalog, source)
        except (ValueError, SectionPurposeValidationError) as exc:
            self.selection_traces.append(
                FrozenSlotSelectionTraceV2_3_4(
                    response_index=len(self.raw_responses),
                    phase="section_purpose_atom_selection_v3",
                    status="rejected_before_claim_plan",
                    slot_count=0,
                    selected_atom_count=0,
                    final_report_request_sent=False,
                )
            )
            raise DeepSeekClientError(f"atom_selection_validation: {exc}") from exc

        isolated = build_isolated_terminal_context(validated)
        context = build_claim_controller_context_v3(validated, isolated)
        self.selection_traces.append(
            FrozenSlotSelectionTraceV2_3_4(
                response_index=len(self.raw_responses),
                phase="section_purpose_atom_selection_v3",
                status="passed",
                slot_count=6,
                selected_atom_count=sum(len(item.selected_atom_ids) for item in validated.slots),
                final_report_request_sent=True,
            )
        )
        schema = json.dumps(
            ClaimStatementResponseV3.model_json_schema(),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        base_messages = [
            {"role": "system", "content": self.prompt + "\n" + schema},
            *original_questions,
            {"role": "user", "content": context.model_visible.model_dump_json()},
        ]
        correction_messages: list[dict[str, Any]] = []
        for repair_index in range(self.claim_repair_limit + 1):
            final = self.delegate.complete_strict_tools(
                messages=base_messages + correction_messages,
                tools=tools,
                tool_choice="none",
                response_format={"type": "json_object"},
            )
            self.runtime_prompt_projection_count += 1
            self.raw_responses.append(final.raw_response)
            try:
                if final.content is None:
                    raise ClaimControllerValidationError(
                        "claim_response_missing", "claim response contains no JSON content"
                    )
                parsed = ClaimStatementResponseV3.model_validate_json(final.content)
                assembled = assemble_final_report_v3(parsed, context, validated)
            except (ValueError, ClaimControllerValidationError) as exc:
                code = getattr(exc, "code", "claim_response_schema_invalid")
                issues = getattr(exc, "issues", [{"code": code, "message": str(exc)}])
                parsed_payload: Any = None
                if final.content:
                    try:
                        parsed_payload = json.loads(final.content)
                    except json.JSONDecodeError:
                        pass
                if repair_index < self.claim_repair_limit:
                    self.terminal_protocol_traces.append(
                        {
                            "status": "repair_requested",
                            "error_code": code,
                            "repair_index": repair_index + 1,
                            "validation_issues": issues,
                            "parsed_model_response": parsed_payload,
                            "mapped_program_response": None,
                        }
                    )
                    feedback = {
                        "phase": "claim_statement_validation_feedback_v3",
                        "repair_attempt": repair_index + 1,
                        "issues": issues,
                        "instruction": (
                            "Return the complete corrected ClaimStatementResponseV3. "
                            "Preserve all IDs and order, copy missing required literals exactly, "
                            "and remove unsupported literals or identifiers."
                        ),
                    }
                    correction_messages = [
                        {"role": "assistant", "content": final.content or "{}"},
                        {"role": "user", "content": json.dumps(feedback, ensure_ascii=False, separators=(",", ":"))},
                    ]
                    continue
                self.terminal_protocol_traces.append(
                    {
                        "status": "failed_stopped",
                        "error_code": code,
                        "validation_issues": issues,
                        "parsed_model_response": parsed_payload,
                        "mapped_program_response": None,
                        "model_visible_claim_plan": context.model_visible.model_dump(mode="json"),
                    }
                )
                raise DeepSeekClientError(
                    f"terminal_protocol_validation: {code}: {exc}"
                ) from exc
            self.terminal_protocol_traces.append(
                {
                    "status": "passed",
                    "error_code": None,
                    "parsed_model_response": parsed.model_dump(mode="json"),
                    "mapped_program_response": assembled.model_dump(mode="json"),
                    "mapped_chart_sources": [
                        [item.chart_plan_id, item.call_id] for item in context.charts
                    ],
                    "model_visible_claim_plan": context.model_visible.model_dump(mode="json"),
                    "claim_controller_version": "v3",
                }
            )
            return replace(final, content=assembled.model_dump_json())
        raise AssertionError("claim repair loop exhausted unexpectedly")


@dataclass
class NativeToolOnlineCandidateClaimControllerV3(
    NativeToolOnlineCandidateCombinedV11
):
    terminal_repair_limit: int = field(init=False, default=1, repr=False)
    real_authorization_validator: Callable[..., None] = field(
        init=False,
        default_factory=lambda: validate_claim_controller_real_authorization,
        repr=False,
    )

    def __post_init__(self) -> None:
        super().__post_init__()
        self.client = ClaimLevelTerminalClientV3(
            self.response_limiter,
            runtime_message_projector=self.runtime_message_projector,
            selection_instruction_builder=self.selection_instruction_builder,
            claim_repair_limit=self.terminal_repair_limit,
        )

    def transport_audit_payload(self) -> dict[str, Any]:
        payload = super().transport_audit_payload()
        payload.update(
            {
                "claim_controller_version": "v3",
                "model_authored_evidence": False,
                "program_bound_claim_evidence": True,
                "program_authored_business_claim_text": False,
                "formal_report_schema_changed": False,
                "fact_schema_changed": False,
            }
        )
        return payload


__all__ = [
    "COMBINED_PROMPT_VERSION", "ClaimLevelTerminalClientV3",
    "NativeToolOnlineCandidateClaimControllerV3",
    "PROMPT_PATH", "validate_claim_controller_real_authorization",
]
