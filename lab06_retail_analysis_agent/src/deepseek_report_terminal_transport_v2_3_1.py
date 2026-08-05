"""V2.3.1 terminal transport with report-admissible evidence projection."""

from __future__ import annotations

from typing import Any

from src.deepseek_report_terminal_transport_v2_3 import (
    DeepSeekReportTerminalTransportV2_3,
)
from src.report_admissible_evidence_projection_v2_3_1 import (
    project_terminal_messages,
)


class DeepSeekReportTerminalTransportV2_3_1(
    DeepSeekReportTerminalTransportV2_3
):
    """Keep V2.3 endpoint isolation and narrow the terminal evidence."""

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
        return (
            projection.messages,
            projection.projected_tool_message_count,
            projection.removed_tool_payload_keys,
            projection.dropped_assistant_tool_call_messages,
            projection.terminal_evidence_envelope_added,
        )

    def audit_payload(self) -> dict[str, Any]:
        payload = super().audit_payload()
        payload["schema_version"] = (
            "1.5.6-h3-deepseek-report-terminal-transport-v2.3.1-audit-v1"
        )
        payload["terminal_evidence_projection"] = (
            "report_admissible_references_v2_3_1"
        )
        payload["full_fact_objects_sent_to_terminal"] = False
        payload["claim_local_validation_changed"] = False
        return payload


__all__ = ["DeepSeekReportTerminalTransportV2_3_1"]
