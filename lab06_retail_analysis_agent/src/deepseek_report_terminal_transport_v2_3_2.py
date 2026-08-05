"""V2.3.2 transport adding deterministic claim evidence bundles."""

from __future__ import annotations

from typing import Any

from src.claim_evidence_bundles_v2_3_2 import (
    build_claim_evidence_envelope,
)
from src.deepseek_client import DeepSeekClientError
from src.deepseek_report_terminal_transport_v2_3_1 import (
    DeepSeekReportTerminalTransportV2_3_1,
)
from src.report_admissible_evidence_projection_v2_3_1 import (
    ReportAdmissibleEnvelopeV2_3_1,
    project_terminal_messages,
)


class DeepSeekReportTerminalTransportV2_3_2(
    DeepSeekReportTerminalTransportV2_3_1
):
    """Keep V2.3.1 projection and add a non-authoring planning layer."""

    @staticmethod
    def _project_terminal_messages(
        messages: list[dict[str, Any]],
    ) -> tuple[
        list[dict[str, Any]],
        int,
        tuple[str, ...],
        int,
        bool,
    ]:
        projection = project_terminal_messages(messages)
        if not projection.terminal_evidence_envelope_added:
            return (
                projection.messages,
                projection.projected_tool_message_count,
                projection.removed_tool_payload_keys,
                projection.dropped_assistant_tool_call_messages,
                False,
            )
        terminal_message = projection.messages[-1]
        content = terminal_message.get("content")
        if terminal_message.get("role") != "user" or not isinstance(content, str):
            raise DeepSeekClientError("V2.3.2 projected envelope is missing")
        try:
            v2_3_1 = ReportAdmissibleEnvelopeV2_3_1.model_validate_json(content)
            v2_3_2 = build_claim_evidence_envelope(v2_3_1)
        except ValueError as exc:
            raise DeepSeekClientError(
                "V2.3.2 claim evidence bundle generation failed"
            ) from exc
        clean = list(projection.messages[:-1])
        clean.append({"role": "user", "content": v2_3_2.model_dump_json()})
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
            "1.5.6-h3-deepseek-report-terminal-transport-v2.3.2-audit-v1"
        )
        payload["claim_evidence_bundle_version"] = "v2.3.2"
        payload["program_authored_claim_text"] = False
        payload["post_hoc_report_repair"] = False
        return payload


__all__ = ["DeepSeekReportTerminalTransportV2_3_2"]
