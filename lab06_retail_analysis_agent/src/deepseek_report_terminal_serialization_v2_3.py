"""Formal offline validation for the V2.3 terminal serialization boundary."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from src.agent_protocol import AgentProtocolError, parse_control_response
from src.deepseek_report_terminal_transport_mock_v2_3 import (
    FrozenNativeLogicalClientV2_3,
    OfflineDeepSeekProviderV2_3,
)
from src.deepseek_report_terminal_transport_v2_3 import (
    BETA_URL,
    STANDARD_URL,
)
from src.fixed_question_validation import (
    load_frozen_questions,
    validate_fixed_question,
)
from src.mock_h2_registry import FrozenH2MockRegistry
from src.mock_native_tool_client_v2_1_revision import (
    FrozenQuestionNativeToolMockClient,
)
from src.online_native_tool_candidate_v2_3 import (
    NativeToolOnlineCandidateV2_3,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DESIGN_PATH = (
    PROJECT_ROOT
    / "config"
    / "h3_deepseek_report_terminal_serialization_v2_3.candidate.json"
)
SAVED_Q02_PATH = (
    PROJECT_ROOT
    / "results"
    / "raw"
    / "q01_q10_batch_a_flash_20260803T233810_455037+0800"
    / "Q02.json"
)
EXPECTED_RESPONSES = {
    "Q01": 2,
    "Q02": 2,
    "Q03": 2,
    "Q04": 2,
    "Q05": 3,
    "Q06": 3,
    "Q07": 3,
    "Q08": 1,
    "Q09": 1,
    "Q10": 1,
}
PASS_LABELS = {
    "protocol_and_dataflow_passed",
    "passed_deterministic_pending_manual_review",
}


class TerminalSerializationV2_3Error(ValueError):
    """Raised when the versioned design or offline evidence drifts."""


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TerminalSerializationV2_3Error(f"object required: {path.name}")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_design() -> dict[str, Any]:
    design = _load_object(DESIGN_PATH)
    selected = design.get("selected_protocol", {})
    business = selected.get("business_tool_phase", {})
    terminal = selected.get("report_or_control_terminal_phase", {})
    fail_closed = design.get("fail_closed_rules", {})
    exclusions = design.get("scope_exclusions", {})
    if (
        design.get("status")
        != "offline_design_authorized_by_user_pending_implementation_validation"
        or business.get("endpoint") != BETA_URL
        or business.get("tools_visible") != 7
        or business.get("tool_choice") != "auto"
        or terminal.get("endpoint") != STANDARD_URL
        or terminal.get("tools_visible") != 0
        or terminal.get("tool_choice_field_sent") is not False
        or terminal.get("response_format") != {"type": "json_object"}
        or terminal.get("report_max_tokens") != 8192
        or terminal.get("clarification_or_boundary_max_tokens") != 4096
        or terminal.get("messages_preserved") is not False
        or terminal.get("terminal_tool_message_projection", {}).get(
            "remove_fields"
        )
        != ["arguments", "result"]
        or terminal.get("clean_terminal_transcript", {}).get(
            "drop_assistant_tool_call_history_from_wire"
        )
        is not True
        or terminal.get("clean_terminal_transcript", {}).get(
            "drop_tool_role_messages_from_wire"
        )
        is not True
        or any(
            fail_closed.get(name) is not False
            for name in (
                "dsml_extraction_allowed",
                "trailing_content_trim_allowed",
                "bare_report_auto_wrapping_allowed",
                "schema_repair_allowed",
            )
        )
        or fail_closed.get("automatic_retry_count") != 0
        or any(value is not False for value in exclusions.values())
    ):
        raise TerminalSerializationV2_3Error("V2.3 design drifted")
    return design


def _saved_q02_probe() -> dict[str, Any]:
    saved = _load_object(SAVED_Q02_PATH)
    raw = saved["outcome"]["raw_responses"][1]
    content = raw["choices"][0]["message"]["content"]
    stripped = content.lstrip()
    prefix, end = json.JSONDecoder().raw_decode(stripped)
    trailing = stripped[end:]
    rejected = False
    try:
        parse_control_response(content)
    except AgentProtocolError:
        rejected = True
    if not (
        rejected
        and raw["choices"][0]["finish_reason"] == "stop"
        and raw["usage"]["completion_tokens"] == 3948
        and prefix.get("schema_version") == "1.5.6-h3-report-draft-v1"
        and "response_type" not in prefix
        and "report" not in prefix
        and "DSML" in trailing
        and "chart_requests" in trailing
    ):
        raise TerminalSerializationV2_3Error(
            "saved Q02 root-cause evidence drifted"
        )
    return {
        "finish_reason": "stop",
        "completion_tokens": 3948,
        "valid_json_prefix_is_bare_report": True,
        "trailing_dsml_chart_requests": True,
        "whole_response_rejected": True,
        "repair_performed": False,
    }


def run_offline_validation(
    output_parent: Path | None = None,
) -> dict[str, Any]:
    validate_design()
    questions = load_frozen_questions()
    cases: list[dict[str, Any]] = []
    total_responses = 0
    total_beta = 0
    total_standard = 0
    for question_id, expected_count in EXPECTED_RESPONSES.items():
        logical = FrozenNativeLogicalClientV2_3(
            FrozenQuestionNativeToolMockClient()
        )
        provider = OfflineDeepSeekProviderV2_3(logical)
        candidate = NativeToolOnlineCandidateV2_3(
            api_key="offline-v2-3-validation-key",
            registry=FrozenH2MockRegistry(),
            response_limit=expected_count,
            transport=provider,
        )
        outcome = candidate.run_turn(
            session_id=f"SESSION-v23-{question_id.lower()}",
            turn_id=f"TURN-{int(question_id[1:]):03d}",
            question=questions[question_id]["question"],
            result_root="results/raw/v2_3_offline_validation",
        )
        fixed = validate_fixed_question(question_id, outcome)
        if fixed.status not in PASS_LABELS:
            raise TerminalSerializationV2_3Error(
                f"{question_id} fixed validation failed: {fixed.status}"
            )
        wire = provider.requests
        if len(wire) != expected_count:
            raise TerminalSerializationV2_3Error(
                f"{question_id} response count drifted"
            )
        terminal = wire[-1]
        if not (
            terminal.endpoint == STANDARD_URL
            and terminal.tool_count == 0
            and terminal.tool_choice_present is False
            and terminal.response_format == {"type": "json_object"}
            and terminal.max_tokens
            == (8192 if question_id <= "Q07" else 4096)
            and candidate.last_trace[-1].visible_tool_names == ()
            and "tool" not in terminal.message_roles
            and "assistant" not in terminal.message_roles
            and all(
                "result" not in keys
                and "arguments" not in keys
                and "facts" in keys
                for keys in terminal.terminal_evidence_call_keys
            )
            and len(terminal.terminal_evidence_call_keys)
            == len(wire) - 1
        ):
            raise TerminalSerializationV2_3Error(
                f"{question_id} terminal wire boundary drifted"
            )
        if any(
            item.endpoint != BETA_URL
            or item.tool_count != 7
            or item.tool_choice != "auto"
            or item.response_format is not None
            for item in wire[:-1]
        ):
            raise TerminalSerializationV2_3Error(
                f"{question_id} business tool wire boundary drifted"
            )
        total_responses += len(wire)
        total_beta += len(wire) - 1
        total_standard += 1
        cases.append(
            {
                "question_id": question_id,
                "status": fixed.status,
                "response_count": len(wire),
                "business_tool_response_count": len(wire) - 1,
                "terminal_endpoint": terminal.endpoint,
                "terminal_tool_count": terminal.tool_count,
                "terminal_tool_choice_sent": terminal.tool_choice_present,
                "terminal_max_tokens": terminal.max_tokens,
                "outcome_status": outcome.status,
            }
        )

    actual_run_id = datetime.now().astimezone().strftime(
        "deepseek_report_terminal_serialization_v2_3_%Y%m%dT%H%M%S_%f%z"
    )
    parent = output_parent or PROJECT_ROOT / "results" / "raw"
    output_dir = parent / actual_run_id
    output_dir.mkdir(parents=True, exist_ok=False)
    summary = {
        "schema_version": (
            "1.5.6-h3-deepseek-report-terminal-serialization-v2.3-"
            "offline-validation-v1"
        ),
        "run_id": actual_run_id,
        "status": "passed",
        "saved_q02_probe": _saved_q02_probe(),
        "question_count": len(cases),
        "questions_passed": len(cases),
        "total_model_responses": total_responses,
        "beta_business_tool_requests": total_beta,
        "standard_json_terminal_requests": total_standard,
        "terminal_requests_with_tools": 0,
        "terminal_requests_with_tool_choice": 0,
        "terminal_raw_tool_results_exposed": False,
        "terminal_raw_tool_arguments_exposed": False,
        "terminal_assistant_tool_call_history_exposed": False,
        "terminal_tool_role_messages_exposed": False,
        "dsml_repair_allowed": False,
        "automatic_retry_count": 0,
        "cases": cases,
        "source_hashes": {
            "design": _sha256(DESIGN_PATH),
            "transport": _sha256(
                PROJECT_ROOT
                / "src"
                / "deepseek_report_terminal_transport_v2_3.py"
            ),
            "candidate": _sha256(
                PROJECT_ROOT / "src" / "online_native_tool_candidate_v2_3.py"
            ),
            "frozen_h2_questions": _sha256(
                PROJECT_ROOT / "config" / "h2_validation_questions.json"
            ),
            "frozen_h2_answers": _sha256(
                PROJECT_ROOT / "data" / "raw" / "h2_reference_answers.json"
            ),
        },
        "real_network_opened": False,
        "real_model_called": False,
        "api_key_read_from_environment": False,
        "h2_changed": False,
        "prompt_file_changed": False,
        "business_tool_schema_changed": False,
        "fact_schema_or_values_changed": False,
        "control_schema_changed": False,
        "acceptance_root_rules_changed": False,
        "batch_b_authorized": False,
        "v2_2_3_resumed": False,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


__all__ = [
    "TerminalSerializationV2_3Error",
    "run_offline_validation",
    "validate_design",
]
