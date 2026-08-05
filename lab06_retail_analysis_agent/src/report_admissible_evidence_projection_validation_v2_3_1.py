"""Formal offline validation of the V2.3.1 report evidence projection."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from src.deepseek_report_terminal_transport_mock_v2_3_1 import (
    OfflineDeepSeekProviderV2_3_1,
    ReportAdmissibleLogicalClientV2_3_1,
)
from src.deepseek_report_terminal_transport_v2_3 import BETA_URL, STANDARD_URL
from src.fixed_question_validation import (
    load_frozen_questions,
    validate_fixed_question,
)
from src.mock_h2_registry import FrozenH2MockRegistry
from src.mock_native_tool_client_v2_1_revision import (
    FrozenQuestionNativeToolMockClient,
)
from src.online_native_tool_candidate_v2_3_1 import (
    NativeToolOnlineCandidateV2_3_1,
)
from src.report_admissible_evidence_projection_v2_3_1 import (
    FORBIDDEN_TERMINAL_KEYS,
    ReportAdmissibleEnvelopeV2_3_1,
    project_terminal_messages,
)
from src.report_validation import (
    REPORT_SECTION_ORDER,
    ReportClaim,
    ReportDraft,
    ReportSection,
    fact_reference,
    validate_report,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DESIGN_PATH = (
    PROJECT_ROOT
    / "config"
    / "h3_report_admissible_evidence_projection_v2_3_1.candidate.json"
)
SAVED_Q02_PATH = (
    PROJECT_ROOT
    / "results"
    / "raw"
    / "q02_terminal_serialization_v2_3_20260804T002004_850300+0800"
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


class ReportAdmissibleValidationError(ValueError):
    """Raised when the versioned design or its offline proof drifts."""


def _object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ReportAdmissibleValidationError(f"object required: {path}")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _walk_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(
            key for item in value.values() for key in _walk_keys(item)
        )
    if isinstance(value, list):
        return {key for item in value for key in _walk_keys(item)}
    return set()


def validate_design() -> dict[str, Any]:
    design = _object(DESIGN_PATH)
    selected = design.get("selected_boundary", {})
    claim_local = design.get("claim_local_evidence_contract", {})
    fail_closed = design.get("fail_closed_rules", {})
    exclusions = design.get("scope_exclusions", {})
    if (
        design.get("status")
        != "offline_implementation_and_validation_completed"
        or selected.get("projection_authority") != "deterministic_program"
        or selected.get("terminal_fact_shape") != "ReportFactReference"
        or selected.get("terminal_request_shape")
        != "ReportRequestReference"
        or selected.get("terminal_policy_shape") != "ReportPolicyReference"
        or selected.get("business_tool_phase_changed") is not False
        or selected.get("local_full_tool_results_preserved") is not True
        or claim_local.get("validation_authority")
        != "existing deterministic report validator"
        or claim_local.get("schema_changed") is not False
        or claim_local.get("each_claim_validated_independently") is not True
        or fail_closed.get("schema_repair_allowed") is not False
        or fail_closed.get("automatic_retry_count") != 0
        or any(value is not False for value in exclusions.values())
    ):
        raise ReportAdmissibleValidationError("V2.3.1 design drifted")
    return design


def _saved_q02_projection_probe() -> dict[str, Any]:
    saved = _object(SAVED_Q02_PATH)
    outcome = saved["outcome"]
    call = outcome["tool_calls"][0]
    source_payload = {
        "internal_call_id": call["call_id"],
        "tool_name": call["tool_name"],
        "arguments": call["arguments"],
        "result": call["result"],
        "facts": call["facts"],
        "request_records": outcome["request_records"],
        "policy_records": outcome["policy_records"],
        "instruction": "historical internal tool instruction",
    }
    source_text = json.dumps(
        source_payload, ensure_ascii=False, separators=(",", ":")
    )
    projection = project_terminal_messages(
        [
            {"role": "system", "content": "offline saved-response probe"},
            {"role": "user", "content": outcome["original_question"]},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": call["provider_call_id"]}],
            },
            {
                "role": "tool",
                "tool_call_id": call["provider_call_id"],
                "content": source_text,
            },
        ]
    )
    envelope_text = projection.messages[-1]["content"]
    envelope = ReportAdmissibleEnvelopeV2_3_1.model_validate_json(
        envelope_text
    )
    leaked = _walk_keys(
        envelope.model_dump(mode="json")["tool_evidence"]
    ) & FORBIDDEN_TERMINAL_KEYS
    historical_codes = {
        item["code"]
        for item in outcome["rejected_report_evidence"][
            "report_validation"
        ]["issues"]
    }
    if not (
        "row_count" in source_text
        and "524878" in source_text
        and "row_count" not in envelope_text
        and "524878" not in envelope_text
        and not leaked
        and projection.dropped_assistant_tool_call_messages == 1
        and projection.removed_tool_payload_keys
        == ("arguments", "instruction", "result")
        and "untraceable_numeric_token" in historical_codes
        and "unsupported_average_value_claim" in historical_codes
    ):
        raise ReportAdmissibleValidationError(
            "saved Q02 projection regression failed"
        )
    return {
        "historical_report_remains_rejected": True,
        "historical_issue_codes": sorted(historical_codes),
        "source_contains_row_count": True,
        "projected_contains_row_count": False,
        "source_contains_observed_value_524878": True,
        "projected_contains_observed_value_524878": False,
        "source_evidence_bytes": projection.source_evidence_bytes,
        "projected_evidence_bytes": projection.projected_evidence_bytes,
        "removed_tool_payload_keys": list(
            projection.removed_tool_payload_keys
        ),
        "schema_or_content_repair_performed": False,
    }


def _claim_local_negative_probe(q02_outcome: Any) -> dict[str, Any]:
    rank_three = next(fact for fact in q02_outcome.facts if fact.rank == 3)
    top_n = next(fact for fact in q02_outcome.facts if fact.metric == "top_n")
    claims = [
        ReportClaim(statement="排名第3。", evidence=[]),
        ReportClaim(statement="3。", evidence=[fact_reference(rank_three)]),
        ReportClaim(statement="前5。", evidence=[]),
        ReportClaim(statement="5。", evidence=[fact_reference(top_n)]),
        ReportClaim(
            statement="平均客单价为123.45英镑。",
            evidence=[fact_reference(item) for item in q02_outcome.facts[:2]],
        ),
    ]
    sections = [
        ReportSection(
            name=name,
            claims=(
                claims
                if index == 0
                else [ReportClaim(statement="没有新增结论。", evidence=[])]
            ),
        )
        for index, name in enumerate(REPORT_SECTION_ORDER)
    ]
    result = validate_report(
        ReportDraft(
            schema_version="1.5.6-h3-report-draft-v1",
            session_id=q02_outcome.session_id,
            turn_id=q02_outcome.turn_id,
            title="局部证据负例",
            sections=sections,
        ),
        list(q02_outcome.facts),
        list(q02_outcome.request_records),
        list(q02_outcome.policy_records),
    )
    messages = [item.message for item in result.issues]
    if not (
        result.status == "failed"
        and any(item.code == "untraceable_numeric_token" for item in result.issues)
        and any("3" in message for message in messages)
        and any("5" in message for message in messages)
        and any("123.45" in message for message in messages)
    ):
        raise ReportAdmissibleValidationError(
            "claim-local evidence negative probe failed"
        )
    return {
        "status": "passed",
        "rank_cannot_borrow_from_another_claim": True,
        "top_n_cannot_borrow_from_another_claim": True,
        "unsupported_arithmetic_remains_rejected": True,
        "validator_schema_changed": False,
    }


def run_offline_validation(
    output_parent: Path | None = None,
) -> dict[str, Any]:
    validate_design()
    questions = load_frozen_questions()
    cases: list[dict[str, Any]] = []
    total_responses = 0
    q02_outcome = None
    for question_id, expected_count in EXPECTED_RESPONSES.items():
        provider = OfflineDeepSeekProviderV2_3_1(
            ReportAdmissibleLogicalClientV2_3_1(
                FrozenQuestionNativeToolMockClient()
            )
        )
        candidate = NativeToolOnlineCandidateV2_3_1(
            api_key="offline-v2-3-1-validation-key",
            registry=FrozenH2MockRegistry(),
            response_limit=expected_count,
            transport=provider,
        )
        outcome = candidate.run_turn(
            session_id=f"SESSION-v231-{question_id.lower()}",
            turn_id=f"TURN-{int(question_id[1:]):03d}",
            question=questions[question_id]["question"],
            result_root="results/raw/v2_3_1_offline_validation",
        )
        fixed = validate_fixed_question(question_id, outcome)
        if fixed.status not in PASS_LABELS:
            raise ReportAdmissibleValidationError(
                f"{question_id} current Harness failed: {fixed.status}"
            )
        wire = provider.requests
        terminal = wire[-1]
        expected_call_count = expected_count - 1
        if not (
            len(wire) == expected_count
            and terminal.endpoint == STANDARD_URL
            and terminal.tool_count == 0
            and terminal.tool_choice_present is False
            and terminal.response_format == {"type": "json_object"}
            and "tool" not in terminal.message_roles
            and candidate.last_trace[-1].visible_tool_names == ()
            and all(
                item.endpoint == BETA_URL
                and item.tool_count == 7
                and item.tool_choice == "auto"
                and item.response_format is None
                for item in wire[:-1]
            )
            and len(terminal.terminal_evidence_call_keys)
            == expected_call_count
            and all(
                set(keys)
                == {
                    "internal_call_id",
                    "tool_name",
                    "fact_references",
                    "request_references",
                    "policy_references",
                }
                for keys in terminal.terminal_evidence_call_keys
            )
        ):
            raise ReportAdmissibleValidationError(
                f"{question_id} V2.3.1 wire boundary drifted"
            )
        if question_id == "Q02":
            q02_outcome = outcome
        total_responses += len(wire)
        cases.append(
            {
                "question_id": question_id,
                "status": fixed.status,
                "outcome_status": outcome.status,
                "response_count": len(wire),
                "business_tool_response_count": len(wire) - 1,
                "terminal_endpoint": terminal.endpoint,
                "terminal_tool_count": terminal.tool_count,
                "terminal_report_admissible_call_count": len(
                    terminal.terminal_evidence_call_keys
                ),
            }
        )
    if q02_outcome is None:
        raise ReportAdmissibleValidationError("Q02 offline outcome missing")

    run_id = datetime.now().astimezone().strftime(
        "report_admissible_evidence_projection_v2_3_1_"
        "%Y%m%dT%H%M%S_%f%z"
    )
    parent = output_parent or PROJECT_ROOT / "results" / "raw"
    output_dir = parent / run_id
    output_dir.mkdir(parents=True, exist_ok=False)
    summary = {
        "schema_version": (
            "1.5.6-h3-report-admissible-evidence-projection-v2.3.1-"
            "offline-validation-v1"
        ),
        "run_id": run_id,
        "status": "passed",
        "saved_q02_projection_probe": _saved_q02_projection_probe(),
        "claim_local_negative_probe": _claim_local_negative_probe(
            q02_outcome
        ),
        "question_count": len(cases),
        "questions_passed": len(cases),
        "total_model_responses": total_responses,
        "beta_business_tool_requests": total_responses - len(cases),
        "standard_json_terminal_requests": len(cases),
        "terminal_requests_with_business_tools": 0,
        "full_fact_objects_sent_to_terminal": False,
        "report_reference_objects_sent_to_terminal": True,
        "automatic_retry_count": 0,
        "cases": cases,
        "source_hashes": {
            "design": _sha256(DESIGN_PATH),
            "projection": _sha256(
                PROJECT_ROOT
                / "src"
                / "report_admissible_evidence_projection_v2_3_1.py"
            ),
            "transport": _sha256(
                PROJECT_ROOT
                / "src"
                / "deepseek_report_terminal_transport_v2_3_1.py"
            ),
            "candidate": _sha256(
                PROJECT_ROOT
                / "src"
                / "online_native_tool_candidate_v2_3_1.py"
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
    "ReportAdmissibleValidationError",
    "run_offline_validation",
    "validate_design",
]
