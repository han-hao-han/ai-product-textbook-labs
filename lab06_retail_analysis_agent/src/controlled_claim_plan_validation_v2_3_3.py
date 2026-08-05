"""Formal offline evidence for the V2.3.3 controlled claim-plan candidate."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from src.claim_evidence_bundles_v2_3_2 import ClaimEvidenceEnvelopeV2_3_2
from src.controlled_claim_plan_mock_v2_3_3 import (
    mock_model_claim_plan,
    mock_model_final_report,
)
from src.controlled_claim_plan_v2_3_3 import (
    ClaimPlanDraftV2_3_3,
    ClaimPlanValidationError,
    validate_claim_plan,
)
from src.deepseek_report_terminal_transport_mock_v2_3_2 import (
    BundleAwareLogicalClientV2_3_2,
    OfflineDeepSeekProviderV2_3_2,
)
from src.fixed_question_validation import load_frozen_questions, validate_fixed_question
from src.mock_h2_registry import FrozenH2MockRegistry
from src.mock_native_tool_client_v2_1_revision import FrozenQuestionNativeToolMockClient
from src.online_native_tool_candidate_v2_3_2 import NativeToolOnlineCandidateV2_3_2
from src.report_validation import validate_report


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_RESPONSES = {
    "Q01": 2, "Q02": 2, "Q03": 2, "Q04": 2, "Q05": 3,
    "Q06": 3, "Q07": 3, "Q08": 1, "Q09": 1, "Q10": 1,
}


class _CapturingProvider(OfflineDeepSeekProviderV2_3_2):
    def __init__(self, logical_client: Any):
        super().__init__(logical_client)
        self.payloads: list[dict[str, Any]] = []

    def __call__(self, url, body, headers, timeout_seconds):
        self.payloads.append(json.loads(body.decode("utf-8")))
        return super().__call__(url, body, headers, timeout_seconds)


def _source_envelope(provider: _CapturingProvider) -> ClaimEvidenceEnvelopeV2_3_2:
    return ClaimEvidenceEnvelopeV2_3_2.model_validate_json(
        provider.payloads[-1]["messages"][-1]["content"]
    )


def _negative_probes(source: ClaimEvidenceEnvelopeV2_3_2) -> dict[str, bool]:
    base = mock_model_claim_plan(source)

    cross_turn_payload = base.model_dump(mode="json")
    cross_turn_payload["turn_id"] = "TURN-999"
    cross_turn_rejected = False
    try:
        validate_claim_plan(
            ClaimPlanDraftV2_3_3.model_validate(cross_turn_payload), source
        )
    except ClaimPlanValidationError:
        cross_turn_rejected = True

    superlative_payload = base.model_dump(mode="json")
    superlative_target = next(
        item for item in superlative_payload["slots"]
        if item["claim_mode"] == "ranked_observation"
    )
    superlative_target["requested_superlative_metric"] = "sales_quantity"
    superlative_rejected = False
    try:
        validate_claim_plan(
            ClaimPlanDraftV2_3_3.model_validate(superlative_payload), source
        )
    except ClaimPlanValidationError:
        superlative_rejected = True

    unknown_payload = base.model_dump(mode="json")
    unknown_payload["slots"][0]["atom_ids"][0] = "ATOM-999"
    unknown_rejected = False
    try:
        validate_claim_plan(
            ClaimPlanDraftV2_3_3.model_validate(unknown_payload), source
        )
    except ClaimPlanValidationError:
        unknown_rejected = True

    text_payload = base.model_dump(mode="json")
    text_payload["slots"][0]["claim_text"] = "forbidden"
    claim_text_rejected = False
    try:
        ClaimPlanDraftV2_3_3.model_validate(text_payload)
    except ValidationError:
        claim_text_rejected = True

    result = {
        "cross_turn_plan_rejected": cross_turn_rejected,
        "quantity_superlative_without_rank_1_quantity_fact_rejected": superlative_rejected,
        "unknown_atom_id_rejected": unknown_rejected,
        "program_or_planner_claim_text_field_rejected": claim_text_rejected,
    }
    if not all(result.values()):
        raise AssertionError("V2.3.3 negative probe failed")
    return result


def run_offline_validation(output_parent: Path | None = None) -> dict[str, Any]:
    questions = load_frozen_questions()
    cases: list[dict[str, Any]] = []
    q02_source: ClaimEvidenceEnvelopeV2_3_2 | None = None
    total_source_fixture_responses = 0
    total_plan_slots = 0
    for question_id, expected in EXPECTED_RESPONSES.items():
        provider = _CapturingProvider(
            BundleAwareLogicalClientV2_3_2(FrozenQuestionNativeToolMockClient())
        )
        candidate = NativeToolOnlineCandidateV2_3_2(
            api_key="offline-v233-validation-key",
            registry=FrozenH2MockRegistry(),
            response_limit=expected,
            transport=provider,
        )
        outcome = candidate.run_turn(
            session_id=f"SESSION-v233-validation-{question_id.lower()}",
            turn_id=f"TURN-{int(question_id[1:]):03d}",
            question=questions[question_id]["question"],
            result_root="results/raw/v2_3_3_offline_validation",
        )
        plan_status = "not_applicable_control_response"
        slot_count = 0
        report_status = (
            None if outcome.report_validation is None else outcome.report_validation.status
        )
        if question_id <= "Q07":
            source = _source_envelope(provider)
            if question_id == "Q02":
                q02_source = source
            draft = mock_model_claim_plan(source)
            validated = validate_claim_plan(draft, source)
            final = mock_model_final_report(validated)
            report_validation = validate_report(
                final.report,
                list(outcome.facts),
                list(outcome.request_records),
                list(outcome.policy_records),
            )
            outcome = replace(
                outcome,
                report_draft=final.report,
                report_validation=report_validation,
            )
            plan_status = "passed"
            slot_count = len(validated.slots)
            total_plan_slots += slot_count
            report_status = report_validation.status
        fixed = validate_fixed_question(question_id, outcome)
        if fixed.status != "passed_deterministic_pending_manual_review":
            raise AssertionError(f"{question_id} V2.3.3 offline Harness failed")
        total_source_fixture_responses += len(provider.requests)
        cases.append(
            {
                "question_id": question_id,
                "status": fixed.status,
                "claim_plan_status": plan_status,
                "claim_plan_slot_count": slot_count,
                "report_validation_status": report_status,
            }
        )
    if q02_source is None:
        raise AssertionError("Q02 source envelope missing")
    q02_plan = validate_claim_plan(mock_model_claim_plan(q02_source), q02_source)
    selection_slots = [
        slot for slot in q02_plan.slots if slot.allowed_selection_limit_values
    ]
    if not (
        len(selection_slots) >= 1
        and any(
            getattr(item, "fact_id", None) == "FACT-001"
            for slot in selection_slots
            for item in slot.allowed_evidence
        )
    ):
        raise AssertionError("Q02 validated selection slot lost FACT-001")
    negatives = _negative_probes(q02_source)

    run_id = datetime.now().astimezone().strftime(
        "controlled_claim_plan_v2_3_3_%Y%m%dT%H%M%S_%f%z"
    )
    output_dir = (output_parent or PROJECT_ROOT / "results" / "raw") / run_id
    output_dir.mkdir(parents=True, exist_ok=False)
    summary = {
        "schema_version": "1.5.6-h3-controlled-claim-plan-v2.3.3-offline-validation-v1",
        "run_id": run_id,
        "status": "passed",
        "question_count": 10,
        "questions_passed": 10,
        "report_questions_with_claim_plan": 7,
        "control_questions_bypassing_claim_plan": 3,
        "source_fixture_response_count": total_source_fixture_responses,
        "simulated_claim_plan_response_count": 7,
        "simulated_final_report_response_count": 7,
        "total_validated_claim_slots": total_plan_slots,
        "q02_selection_limit_fact_id": "FACT-001",
        "negative_probes": negatives,
        "cases": cases,
        "production_transport_integrated": False,
        "future_q02_response_count_if_integrated": 3,
        "program_authored_claim_text": False,
        "program_calculated_business_value": False,
        "post_hoc_report_repair": False,
        "h2_data_prompt_tool_fact_report_schema_changed": False,
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
