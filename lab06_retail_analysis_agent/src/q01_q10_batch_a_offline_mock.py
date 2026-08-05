"""Evidence-complete offline model double for frozen batch A."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.agent_protocol import ChartRequest, FinalReportResponse
from src.deepseek_client import ChatCompletionResult, ProviderToolCall
from src.deepseek_provider_schema_adapter_v2_1_revision import (
    DEEPSEEK_NONE_SENTINEL,
    NULLABLE_ARGUMENT_FIELDS,
)
from src.evidence_provenance import PolicyRecord, RequestRecord
from src.fact_schema import FactRecord
from src.fixed_question_validation import load_frozen_questions
from src.mock_native_tool_client_v2_1_revision import (
    FrozenQuestionNativeToolMockClient,
    _result,
    _tool_payloads,
)
from src.report_validation import (
    REPORT_SECTION_ORDER,
    ReportClaim,
    ReportDraft,
    ReportSection,
    fact_reference,
    policy_reference,
    request_reference,
)


BATCH_A_QUESTION_IDS = ("Q02", "Q06", "Q08", "Q09", "Q10")


def _flatten(value: Any) -> list[Any]:
    if isinstance(value, dict):
        return [leaf for item in value.values() for leaf in _flatten(item)]
    if isinstance(value, list):
        return [leaf for item in value for leaf in _flatten(item)]
    return [value]


def _unique_records(
    payloads: list[dict[str, Any]],
    key: str,
    model: type[RequestRecord] | type[PolicyRecord],
    id_field: str,
) -> list[RequestRecord] | list[PolicyRecord]:
    records: dict[str, RequestRecord | PolicyRecord] = {}
    for payload in payloads:
        for raw in payload.get(key, []):
            record = model.model_validate(raw)
            records[str(getattr(record, id_field))] = record
    return list(records.values())


def _complete_report_response(
    messages: list[dict[str, Any]],
    question_id: str,
) -> ChatCompletionResult:
    payloads = _tool_payloads(messages)
    facts = [
        FactRecord.model_validate(raw)
        for payload in payloads
        for raw in payload.get("facts", [])
    ]
    requests = _unique_records(
        payloads, "request_records", RequestRecord, "request_id"
    )
    policies = _unique_records(
        payloads, "policy_records", PolicyRecord, "policy_id"
    )
    answer = load_frozen_questions()[question_id]["reference_answer"]
    statement = "；".join(str(value) for value in _flatten(answer))
    if question_id == "Q06":
        statement += "；3"
    evidence = [fact_reference(item) for item in facts]
    evidence.extend(request_reference(item) for item in requests)
    evidence.extend(policy_reference(item) for item in policies)
    claims = {
        name: ReportClaim(statement="本节不新增数值结论。", evidence=[])
        for name in REPORT_SECTION_ORDER
    }
    claims["关键经营发现"] = ReportClaim(
        statement=statement,
        evidence=evidence,
    )
    report = ReportDraft(
        schema_version="1.5.6-h3-report-draft-v1",
        session_id=facts[0].session_id,
        turn_id=facts[0].turn_id,
        title=f"{question_id} 离线完整证据报告",
        sections=[
            ReportSection(name=name, claims=[claims[name]])
            for name in REPORT_SECTION_ORDER
        ],
    )
    chart_types = {
        "rank_products": "top_n_horizontal_bar",
        "analyze_time_trend": "monthly_line",
    }
    charts = [
        ChartRequest(
            call_id=payload["internal_call_id"],
            chart_type=chart_types[payload["tool_name"]],
            title=f"{payload['tool_name']} 离线确定性图表",
        )
        for payload in payloads
        if payload.get("tool_name") in chart_types
    ]
    return _result(
        content=FinalReportResponse(
            response_type="report",
            report=report,
            chart_requests=charts,
        ).model_dump_json()
    )


@dataclass
class BatchAEvidenceCompleteMockClient:
    """Simulate provider decisions while Pandas/tool code remains real."""

    delegate: FrozenQuestionNativeToolMockClient = field(
        default_factory=FrozenQuestionNativeToolMockClient
    )

    def complete_strict_tools(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: str = "auto",
        response_format: dict[str, str] | None = None,
    ) -> ChatCompletionResult:
        question_by_text = {
            item["question"]: question_id
            for question_id, item in load_frozen_questions().items()
        }
        user_question = next(
            message["content"]
            for message in messages
            if message.get("role") == "user"
        )
        question_id = question_by_text[user_question]
        payload_count = len(_tool_payloads(messages))
        if (
            question_id == "Q02" and payload_count == 1
        ) or (
            question_id == "Q06" and payload_count == 2
        ):
            return _complete_report_response(messages, question_id)

        result = self.delegate.complete_strict_tools(
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
            response_format=response_format,
        )
        if not result.tool_calls:
            return result
        selected = result.tool_calls[0]
        arguments = dict(selected.arguments)
        for field_name in NULLABLE_ARGUMENT_FIELDS.get(
            selected.tool_name, frozenset()
        ):
            if arguments.get(field_name) is None:
                arguments[field_name] = DEEPSEEK_NONE_SENTINEL
        return ChatCompletionResult(
            finish_reason=result.finish_reason,
            content=result.content,
            tool_calls=(
                ProviderToolCall(
                    provider_call_id=selected.provider_call_id,
                    tool_name=selected.tool_name,
                    arguments=arguments,
                ),
            ),
            raw_response={
                **result.raw_response,
                "batch_a_provider_schema_mock": True,
            },
            usage=result.usage,
        )
