"""Formal integrated transport validation for V2.3.3."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from src.deepseek_controlled_claim_plan_transport_mock_v2_3_3 import (
    ControlledClaimPlanLogicalClientV2_3_3,
    OfflineDeepSeekProviderV2_3_3,
)
from src.fixed_question_validation import load_frozen_questions, validate_fixed_question
from src.mock_h2_registry import FrozenH2MockRegistry
from src.mock_native_tool_client_v2_1_revision import FrozenQuestionNativeToolMockClient
from src.online_native_tool_candidate_v2_3_3 import NativeToolOnlineCandidateV2_3_3


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "Q01": 3, "Q02": 3, "Q03": 3, "Q04": 3, "Q05": 4,
    "Q06": 4, "Q07": 4, "Q08": 1, "Q09": 1, "Q10": 1,
}


def _candidate(question_id: str, plan_mutator=None):
    provider = OfflineDeepSeekProviderV2_3_3(
        ControlledClaimPlanLogicalClientV2_3_3(
            FrozenQuestionNativeToolMockClient(), plan_mutator=plan_mutator
        )
    )
    candidate = NativeToolOnlineCandidateV2_3_3(
        api_key="offline-v233-transport-validation-key",
        registry=FrozenH2MockRegistry(),
        response_limit=EXPECTED[question_id],
        transport=provider,
    )
    return candidate, provider


def run_offline_validation(output_parent: Path | None = None) -> dict:
    questions = load_frozen_questions()
    cases = []
    total = 0
    for question_id, expected in EXPECTED.items():
        candidate, provider = _candidate(question_id)
        outcome = candidate.run_turn(
            session_id=f"SESSION-v233-transport-{question_id.lower()}",
            turn_id=f"TURN-{int(question_id[1:]):03d}",
            question=questions[question_id]["question"],
            result_root="results/raw/v2_3_3_transport_validation",
        )
        fixed = validate_fixed_question(question_id, outcome)
        snapshot = candidate.response_limit_snapshot()
        if not (
            fixed.status == "passed_deterministic_pending_manual_review"
            and snapshot.attempted == expected
            and snapshot.completed == expected
            and snapshot.failed == 0
            and len(provider.requests) == expected
        ):
            raise AssertionError(f"{question_id} integrated V2.3.3 failed")
        phases = candidate.transport_audit_payload()["request_phases"]
        if question_id <= "Q07" and phases[-2:] != [
            "controlled_claim_plan_generation",
            "final_report_from_validated_claim_plan",
        ]:
            raise AssertionError(f"{question_id} V2.3.3 phases drifted")
        total += expected
        cases.append(
            {
                "question_id": question_id,
                "status": fixed.status,
                "response_count": expected,
                "request_phases": phases,
                "claim_plan_trace_count": len(candidate.claim_plan_trace),
            }
        )

    def invalidate(payload):
        target = next(
            item for item in payload["slots"]
            if item["claim_mode"] == "ranked_observation"
        )
        target["requested_superlative_metric"] = "sales_quantity"
        return payload

    failed_candidate, failed_provider = _candidate("Q02", invalidate)
    failed = failed_candidate.run_turn(
        session_id="SESSION-v233-transport-invalid-q02",
        turn_id="TURN-002",
        question=questions["Q02"]["question"],
        result_root="results/raw/v2_3_3_transport_invalid",
    )
    failure_snapshot = failed_candidate.response_limit_snapshot()
    negative = {
        "status": failed.status,
        "error_stage": failed.error_stage,
        "responses_attempted": failure_snapshot.attempted,
        "responses_completed": failure_snapshot.completed,
        "provider_requests": len(failed_provider.requests),
        "final_report_request_sent": failed_candidate.claim_plan_trace[0].final_report_request_sent,
        "request_phases": failed_candidate.transport_audit_payload()["request_phases"],
    }
    if negative != {
        "status": "failed",
        "error_stage": "claim_plan_validation",
        "responses_attempted": 2,
        "responses_completed": 2,
        "provider_requests": 2,
        "final_report_request_sent": False,
        "request_phases": [
            "business_tool_selection",
            "controlled_claim_plan_generation",
        ],
    }:
        raise AssertionError("invalid Q02 plan did not stop before final report")

    run_id = datetime.now().astimezone().strftime(
        "controlled_claim_plan_transport_v2_3_3_%Y%m%dT%H%M%S_%f%z"
    )
    output_dir = (output_parent or PROJECT_ROOT / "results" / "raw") / run_id
    output_dir.mkdir(parents=True, exist_ok=False)
    summary = {
        "schema_version": "1.5.6-h3-controlled-claim-plan-transport-v2.3.3-offline-validation-v1",
        "run_id": run_id,
        "status": "passed",
        "questions_passed": 10,
        "total_counted_model_responses": total,
        "expected_response_counts": EXPECTED,
        "cases": cases,
        "invalid_q02_plan_probe": negative,
        "production_candidate_wired": True,
        "response_limiter_counts_plan_and_final_separately": True,
        "invalid_plan_stops_before_final_report": True,
        "program_authored_claim_text": False,
        "post_hoc_report_repair": False,
        "h2_data_frozen_prompt_tool_fact_report_schema_changed": False,
        "harness_root_rules_changed": False,
        "real_network_opened": False,
        "real_model_called": False,
        "v2_2_3_resumed": False,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


__all__ = ["run_offline_validation"]
