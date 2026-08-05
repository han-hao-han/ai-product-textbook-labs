"""V2.3.4.2 transport: keep internal CALL identifiers off the model wire."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import Any

from src.deepseek_client import DeepSeekClientError, HttpResponseData, HttpTransport
from src.deepseek_section_purpose_transport_v2_3_4_1 import (
    DeepSeekSectionPurposeTransportV2_3_4_1,
    _json_phase,
)
from src.report_admissible_evidence_projection_v2_3_1 import (
    ReportAdmissibleEnvelopeV2_3_1,
    project_terminal_messages,
)
from src.report_terminal_protocol_guard_v2_3_4_2 import (
    INTERNAL_CALL_VALUE_PATTERN,
    ValidatedModelVisibleEnvelopeV2_3_4_2,
)


@dataclass(frozen=True)
class ModelVisibilityAuditV2_3_4_2:
    request_index: int
    removed_internal_field_paths: tuple[str, ...]
    model_visible_internal_call_values: int
    outbound_model_message_count: int


def _strip_internal_fields(value: Any, *, path: str, removed: list[str]) -> Any:
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            if key in {"internal_call_id", "call_id", "source_result_path"}:
                removed.append(child_path)
                continue
            clean[key] = _strip_internal_fields(
                child, path=child_path, removed=removed
            )
        return clean
    if isinstance(value, list):
        return [
            _strip_internal_fields(
                child, path=f"{path}[{index}]", removed=removed
            )
            for index, child in enumerate(value)
        ]
    return value


@dataclass
class ModelVisibleCallIsolationTransportV2_3_4_2:
    delegate: HttpTransport
    requests: list[ModelVisibilityAuditV2_3_4_2] = field(default_factory=list)

    def __call__(
        self,
        url: str,
        body: bytes,
        headers: dict[str, str],
        timeout_seconds: float,
    ) -> HttpResponseData:
        try:
            payload = json.loads(body.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DeepSeekClientError(
                "V2.3.4.2 visibility boundary received invalid JSON"
            ) from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("messages"), list):
            raise DeepSeekClientError(
                "V2.3.4.2 visibility boundary requires model messages"
            )
        outbound = deepcopy(payload)
        removed: list[str] = []
        clean_messages: list[dict[str, Any]] = []
        for index, message in enumerate(outbound["messages"]):
            if not isinstance(message, dict):
                raise DeepSeekClientError("model message must be an object")
            copied = deepcopy(message)
            if copied.get("role") == "tool" and isinstance(copied.get("content"), str):
                try:
                    tool_payload = json.loads(copied["content"])
                except json.JSONDecodeError as exc:
                    raise DeepSeekClientError(
                        "tool message content is not valid JSON"
                    ) from exc
                sanitized = _strip_internal_fields(
                    tool_payload,
                    path=f"messages[{index}].content",
                    removed=removed,
                )
                copied["content"] = json.dumps(
                    sanitized, ensure_ascii=False, separators=(",", ":")
                )
            clean_messages.append(copied)
        outbound["messages"] = clean_messages
        visible_text = json.dumps(
            clean_messages, ensure_ascii=False, separators=(",", ":")
        )
        leaks = len(INTERNAL_CALL_VALUE_PATTERN.findall(visible_text))
        self.requests.append(
            ModelVisibilityAuditV2_3_4_2(
                request_index=len(self.requests) + 1,
                removed_internal_field_paths=tuple(removed),
                model_visible_internal_call_values=leaks,
                outbound_model_message_count=len(clean_messages),
            )
        )
        if leaks:
            raise DeepSeekClientError(
                "model_visible_internal_call_id: outbound messages still contain CALL values"
            )
        return self.delegate(
            url,
            json.dumps(
                outbound, ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8"),
            headers,
            timeout_seconds,
        )

    def audit_payload(self) -> dict[str, Any]:
        return {
            "schema_version": "1.5.6-h3-model-visible-call-isolation-v2.3.4.2-audit-v1",
            "request_count": len(self.requests),
            "model_visible_internal_call_values": sum(
                item.model_visible_internal_call_values for item in self.requests
            ),
            "all_model_visible_internal_call_counts_zero": all(
                item.model_visible_internal_call_values == 0
                for item in self.requests
            ),
            "requests": [asdict(item) for item in self.requests],
            "request_body_saved": False,
            "request_headers_saved": False,
        }


@dataclass
class DeepSeekInternalCallIsolationTransportV2_3_4_2(
    DeepSeekSectionPurposeTransportV2_3_4_1
):
    """Project a public terminal envelope while retaining internal validation."""

    def __call__(self, url, body, headers, timeout_seconds) -> HttpResponseData:
        try:
            payload = json.loads(body.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DeepSeekClientError("V2.3.4.2 transport received invalid JSON") from exc
        messages = payload.get("messages") if isinstance(payload, dict) else []
        has_public_terminal = any(
            isinstance(item, dict)
            and _json_phase(item)
            == "report_terminal_validated_section_purpose_slots_v2_3_4_2"
            for item in messages
        )
        response = super().__call__(url, body, headers, timeout_seconds)
        if has_public_terminal and self.v2_3_4_1_phases:
            self.v2_3_4_1_phases[-1] = (
                "final_report_from_call_isolated_section_purpose_slots"
            )
        return response

    @staticmethod
    def _project_terminal_messages(messages: list[dict[str, Any]]):
        public_messages = [
            item
            for item in messages
            if _json_phase(item)
            == "report_terminal_validated_section_purpose_slots_v2_3_4_2"
        ]
        catalog_messages = [
            item
            for item in messages
            if _json_phase(item) == "frozen_six_slot_section_purpose_catalog"
        ]
        if catalog_messages and not public_messages:
            if len(catalog_messages) != 1:
                raise DeepSeekClientError(
                    "V2.3.4.2 requires exactly one purpose catalog"
                )
            visible = json.dumps(messages, ensure_ascii=False, separators=(",", ":"))
            if INTERNAL_CALL_VALUE_PATTERN.search(visible):
                raise DeepSeekClientError("model_visible_internal_call_id in catalog request")
            return list(messages), 0, (), 0, True
        if not public_messages:
            return DeepSeekSectionPurposeTransportV2_3_4_1._project_terminal_messages(
                messages
            )
        if len(public_messages) != 1:
            raise DeepSeekClientError(
                "V2.3.4.2 requires exactly one public terminal envelope"
            )
        try:
            public = ValidatedModelVisibleEnvelopeV2_3_4_2.model_validate_json(
                public_messages[0]["content"]
            )
        except (KeyError, ValueError) as exc:
            raise DeepSeekClientError(
                "V2.3.4.2 public terminal envelope failed Schema validation"
            ) from exc
        source_messages = [
            item for item in messages if item is not public_messages[0]
        ]
        projection = project_terminal_messages(source_messages)
        if not projection.terminal_evidence_envelope_added:
            raise DeepSeekClientError(
                "V2.3.4.2 final report lacks current-turn evidence"
            )
        try:
            source = ReportAdmissibleEnvelopeV2_3_1.model_validate_json(
                projection.messages[-1]["content"]
            )
        except (KeyError, ValueError) as exc:
            raise DeepSeekClientError("V2.3.4.2 source projection is missing") from exc
        if (source.session_id, source.turn_id) != (public.session_id, public.turn_id):
            raise DeepSeekClientError(
                "V2.3.4.2 public envelope crosses session or turn"
            )
        clean = list(projection.messages[:-1])
        clean.append({"role": "user", "content": public.model_dump_json()})
        visible = json.dumps(clean, ensure_ascii=False, separators=(",", ":"))
        if INTERNAL_CALL_VALUE_PATTERN.search(visible):
            raise DeepSeekClientError(
                "model_visible_internal_call_id in terminal request"
            )
        return (
            clean,
            projection.projected_tool_message_count,
            projection.removed_tool_payload_keys,
            projection.dropped_assistant_tool_call_messages,
            True,
        )

    def audit_payload(self) -> dict[str, Any]:
        payload = super().audit_payload()
        payload["schema_version"] = (
            "1.5.6-h3-internal-call-isolation-transport-v2.3.4.2-audit-v1"
        )
        payload["terminal_projection_internal_call_id_values"] = 0
        payload["chart_source_alias_version"] = "v2.3.4.2"
        return payload


__all__ = [
    "DeepSeekInternalCallIsolationTransportV2_3_4_2",
    "ModelVisibleCallIsolationTransportV2_3_4_2",
]
