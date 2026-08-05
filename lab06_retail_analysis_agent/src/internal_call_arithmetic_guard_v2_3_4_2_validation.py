"""Run the network-free V2.3.4.2 Q01-Q10 evidence audit."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Type

from src.deepseek_internal_call_isolation_transport_mock_v2_3_4_2 import (
    CallIsolatedFrozenQuestionNativeToolMockClient,
    CallIsolatedLogicalClientV2_3_4_2,
    OfflineDeepSeekProviderV2_3_4_2,
)
from src.fixed_question_validation import (
    load_frozen_questions,
    validate_fixed_question,
)
from src.mock_h2_registry import FrozenH2MockRegistry
from src.online_native_tool_candidate_v2_3_4_2 import (
    NativeToolOnlineCandidateV2_3_4_2,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_RESPONSES = {
    "Q01": 3,
    "Q02": 3,
    "Q03": 3,
    "Q04": 3,
    "Q05": 4,
    "Q06": 4,
    "Q07": 4,
    "Q08": 1,
    "Q09": 1,
    "Q10": 1,
}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def run_offline_validation(
    output_dir: Path,
    *,
    candidate_type: Type[NativeToolOnlineCandidateV2_3_4_2] = (
        NativeToolOnlineCandidateV2_3_4_2
    ),
    audit_schema_version: str = (
        "1.5.6-h3-v2.3.4.2-offline-audit-summary-v1"
    ),
    case_schema_version: str = "1.5.6-h3-v2.3.4.2-offline-case-v1",
    session_prefix: str = "v2342-audit",
    result_root: str = "results/raw/v2_3_4_2_offline_validation",
) -> dict[str, Any]:
    questions = load_frozen_questions()
    cases: list[dict[str, Any]] = []
    failures: list[str] = []
    for question_id, expected_responses in EXPECTED_RESPONSES.items():
        logical = CallIsolatedLogicalClientV2_3_4_2(
            CallIsolatedFrozenQuestionNativeToolMockClient()
        )
        provider = OfflineDeepSeekProviderV2_3_4_2(logical)
        candidate = candidate_type(
            api_key="offline-validation-key-not-real",
            registry=FrozenH2MockRegistry(),
            response_limit=expected_responses,
            transport=provider,
        )
        outcome = candidate.run_turn(
            session_id=f"SESSION-{session_prefix}-{question_id.lower()}",
            turn_id=f"TURN-{int(question_id[1:]):03d}",
            question=questions[question_id]["question"],
            result_root=result_root,
        )
        fixed = validate_fixed_question(question_id, outcome)
        snapshot = candidate.response_limit_snapshot()
        audit = candidate.transport_audit_payload()
        case_failures: list[str] = []
        expected_fixed = "passed_deterministic_pending_manual_review"
        if fixed.status != expected_fixed:
            case_failures.append("fixed_question_acceptance_failed")
        if (snapshot.attempted, snapshot.completed, snapshot.failed) != (
            expected_responses,
            expected_responses,
            0,
        ):
            case_failures.append("response_accounting_mismatch")
        if len(provider.requests) != expected_responses:
            case_failures.append("provider_request_count_mismatch")
        visibility = audit["model_visibility"]
        if not visibility["all_model_visible_internal_call_counts_zero"]:
            case_failures.append("model_visible_internal_call_id")
        if question_id <= "Q07":
            if len(candidate.terminal_protocol_trace) != 1:
                case_failures.append("terminal_protocol_trace_missing")
            elif candidate.terminal_protocol_trace[0]["status"] != "passed":
                case_failures.append("terminal_protocol_mapping_failed")
            elif not (
                candidate.terminal_protocol_trace[0].get(
                    "parsed_model_response"
                )
                and candidate.terminal_protocol_trace[0].get(
                    "mapped_program_response"
                )
            ):
                case_failures.append("raw_parsed_mapped_evidence_missing")
        elif candidate.terminal_protocol_trace:
            case_failures.append("unexpected_terminal_protocol_trace")
        if case_failures:
            failures.extend(f"{question_id}:{item}" for item in case_failures)
        case = {
            "schema_version": case_schema_version,
            "question_id": question_id,
            "status": "passed" if not case_failures else "failed",
            "failures": case_failures,
            "outcome_status": outcome.status,
            "fixed_question_status": fixed.status,
            "fixed_question_issues": [
                item.model_dump(mode="json") for item in fixed.issues
            ],
            "response_accounting": {
                "attempted": snapshot.attempted,
                "completed": snapshot.completed,
                "failed": snapshot.failed,
            },
            "tool_names": [item.tool_name for item in outcome.tool_calls],
            "fact_count": len(outcome.facts),
            "chart_count": len(outcome.charts),
            "report_validation_status": (
                outcome.report_validation.status
                if outcome.report_validation is not None
                else None
            ),
            "raw_provider_responses": list(outcome.raw_responses),
            "terminal_protocol_trace": list(candidate.terminal_protocol_trace),
            "transport_audit": audit,
            "privacy": {
                "real_model_called": False,
                "network_used": False,
                "api_key_read_from_environment": False,
                "authorization_header_saved": False,
                "request_body_saved": False,
                "raw_customer_id_exported": False,
            },
        }
        _write_json(output_dir / f"{question_id}.json", case)
        cases.append(case)
    summary = {
        "schema_version": audit_schema_version,
        "run_id": output_dir.name,
        "status": "passed" if not failures else "failed",
        "question_ids": list(EXPECTED_RESPONSES),
        "passed_question_count": sum(item["status"] == "passed" for item in cases),
        "failed_question_count": sum(item["status"] == "failed" for item in cases),
        "failures": failures,
        "total_model_responses": sum(
            item["response_accounting"]["attempted"] for item in cases
        ),
        "model_visible_internal_call_values": sum(
            item["transport_audit"]["model_visibility"].get(
                "model_visible_internal_call_values", 0
            )
            for item in cases
        ),
        "raw_parsed_mapped_saved_separately": all(
            item["question_id"] > "Q07"
            or (
                len(item["terminal_protocol_trace"]) == 1
                and bool(
                    item["terminal_protocol_trace"][0].get(
                        "parsed_model_response"
                    )
                )
                and bool(
                    item["terminal_protocol_trace"][0].get(
                        "mapped_program_response"
                    )
                )
            )
            for item in cases
        ),
        "formal_report_schema_changed": False,
        "fact_schema_changed": False,
        "h2_reference_answers_changed": False,
        "business_tool_schemas_changed": False,
        "post_hoc_report_prose_repair": False,
        "real_model_called": False,
        "network_used": False,
        "api_key_read": False,
        "v2_2_3_resumed": False,
    }
    _write_json(output_dir / "summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    output_dir = args.output_dir or (
        PROJECT_ROOT
        / "results"
        / "raw"
        / datetime.now().astimezone().strftime(
            "internal_call_arithmetic_guard_v2_3_4_2_offline_%Y%m%dT%H%M%S_%f%z"
        )
    )
    summary = run_offline_validation(output_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
