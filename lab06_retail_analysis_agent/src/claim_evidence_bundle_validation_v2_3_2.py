"""Formal offline validation for the V2.3.2 bundle implementation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from src.claim_evidence_bundles_v2_3_2 import (
    ClaimEvidenceEnvelopeV2_3_2,
    build_claim_evidence_bundles,
)
from src.claim_local_evidence_bundle_design_v2_3_2 import validate_design
from src.deepseek_report_terminal_transport_mock_v2_3_2 import (
    BundleAwareLogicalClientV2_3_2,
    OfflineDeepSeekProviderV2_3_2,
)
from src.fixed_question_validation import (
    load_frozen_questions,
    validate_fixed_question,
)
from src.mock_h2_registry import FrozenH2MockRegistry
from src.mock_native_tool_client_v2_1_revision import (
    FrozenQuestionNativeToolMockClient,
)
from src.online_native_tool_candidate_v2_3_2 import (
    NativeToolOnlineCandidateV2_3_2,
)
from src.report_admissible_evidence_projection_v2_3_1 import (
    ReportAdmissibleEnvelopeV2_3_1,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DESIGN_PATH = (
    PROJECT_ROOT
    / "config"
    / "h3_claim_local_evidence_bundle_v2_3_2.candidate.json"
)
REAL_AUDIT_PATH = (
    PROJECT_ROOT
    / "results"
    / "raw"
    / "batch_a_report_admissible_v2_3_1_20260804T131120_351077+0800"
    / "concentrated_audit.json"
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


class BundleImplementationValidationError(ValueError):
    """Raised when V2.3.2 implementation evidence drifts."""


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise BundleImplementationValidationError(f"object required: {path}")
    return value


class _CapturingProvider(OfflineDeepSeekProviderV2_3_2):
    def __init__(self, logical_client: Any):
        super().__init__(logical_client)
        self.envelopes: list[ClaimEvidenceEnvelopeV2_3_2] = []

    def __call__(self, url, body, headers, timeout_seconds):
        payload = json.loads(body.decode("utf-8"))
        for message in reversed(payload.get("messages", [])):
            if message.get("role") != "user":
                continue
            content = message.get("content")
            if not isinstance(content, str):
                continue
            try:
                candidate = json.loads(content)
            except json.JSONDecodeError:
                continue
            if (
                isinstance(candidate, dict)
                and candidate.get("phase")
                == "report_terminal_claim_evidence_bundles"
            ):
                self.envelopes.append(
                    ClaimEvidenceEnvelopeV2_3_2.model_validate(candidate)
                )
                break
        return super().__call__(url, body, headers, timeout_seconds)


def _negative_probes(
    q02: ClaimEvidenceEnvelopeV2_3_2,
    q06: ClaimEvidenceEnvelopeV2_3_2,
) -> dict[str, bool]:
    unknown = q02.model_dump(mode="json")
    unknown["claim_evidence_bundles"][0]["support_atoms"][0][
        "evidence_ids"
    ] = ["FACT-999"]
    unknown_rejected = False
    try:
        ClaimEvidenceEnvelopeV2_3_2.model_validate(unknown)
    except ValidationError:
        unknown_rejected = True

    authored = q02.model_dump(mode="json")
    authored["claim_evidence_bundles"][0]["claim_text"] = "前5商品"
    authored_text_rejected = False
    try:
        ClaimEvidenceEnvelopeV2_3_2.model_validate(authored)
    except ValidationError:
        authored_text_rejected = True

    v231 = ReportAdmissibleEnvelopeV2_3_1(
        phase="report_terminal_admissible_evidence",
        session_id=q06.session_id,
        turn_id=q06.turn_id,
        tool_evidence=q06.tool_evidence,
    )
    second = v231.tool_evidence[1]
    drifted = second.model_copy(
        update={
            "fact_references": [
                item.model_copy(update={"start_date": "2011-10-01"})
                for item in second.fact_references
            ]
        }
    )
    drifted_envelope = v231.model_copy(
        update={"tool_evidence": [v231.tool_evidence[0], drifted]}
    )
    ambiguous_cross_tool_not_bundled = not any(
        item.bundle_kind == "cross_tool_observation"
        for item in build_claim_evidence_bundles(drifted_envelope)
    )
    saved_real = _object(REAL_AUDIT_PATH)
    saved_q02_remains_rejected = (
        saved_real["status"] == "root_cause_confirmed"
        and saved_real["root_failure"]["unsupported_token"] == "5"
        and saved_real["root_failure"]["required_local_evidence_id"]
        == "FACT-001"
        and saved_real["root_failure"][
            "required_local_evidence_was_missing_from_failed_claim"
        ]
        is True
    )
    result = {
        "unknown_evidence_rejected": unknown_rejected,
        "program_authored_claim_text_rejected": authored_text_rejected,
        "ambiguous_cross_tool_join_not_bundled": (
            ambiguous_cross_tool_not_bundled
        ),
        "saved_real_q02_remains_rejected_without_repair": (
            saved_q02_remains_rejected
        ),
    }
    if not all(result.values()):
        raise BundleImplementationValidationError(
            "V2.3.2 negative probe failed"
        )
    return result


def run_offline_validation(
    output_parent: Path | None = None,
) -> dict[str, Any]:
    design_audit = validate_design()
    questions = load_frozen_questions()
    cases: list[dict[str, Any]] = []
    envelopes: dict[str, ClaimEvidenceEnvelopeV2_3_2] = {}
    total_responses = 0
    total_bundles = 0
    for question_id, expected_count in EXPECTED_RESPONSES.items():
        provider = _CapturingProvider(
            BundleAwareLogicalClientV2_3_2(
                FrozenQuestionNativeToolMockClient()
            )
        )
        candidate = NativeToolOnlineCandidateV2_3_2(
            api_key="offline-v2-3-2-validation-key",
            registry=FrozenH2MockRegistry(),
            response_limit=expected_count,
            transport=provider,
        )
        outcome = candidate.run_turn(
            session_id=f"SESSION-v232-{question_id.lower()}",
            turn_id=f"TURN-{int(question_id[1:]):03d}",
            question=questions[question_id]["question"],
            result_root="results/raw/v2_3_2_offline_validation",
        )
        fixed = validate_fixed_question(question_id, outcome)
        if fixed.status != "passed_deterministic_pending_manual_review":
            raise BundleImplementationValidationError(
                f"{question_id} current Harness failed: {fixed.status}"
            )
        if len(provider.requests) != expected_count:
            raise BundleImplementationValidationError(
                f"{question_id} response count drifted"
            )
        if question_id <= "Q07":
            if len(provider.envelopes) != 1:
                raise BundleImplementationValidationError(
                    f"{question_id} terminal bundle envelope missing"
                )
            envelopes[question_id] = provider.envelopes[0]
            total_bundles += len(
                provider.envelopes[0].claim_evidence_bundles
            )
        elif provider.envelopes:
            raise BundleImplementationValidationError(
                f"{question_id} control response must not invent bundles"
            )
        total_responses += len(provider.requests)
        cases.append(
            {
                "question_id": question_id,
                "status": fixed.status,
                "response_count": len(provider.requests),
                "outcome_status": outcome.status,
                "bundle_count": (
                    len(provider.envelopes[0].claim_evidence_bundles)
                    if provider.envelopes
                    else 0
                ),
            }
        )

    q02_selection = [
        item
        for item in envelopes["Q02"].claim_evidence_bundles
        if item.bundle_kind == "selection_limit"
    ]
    q06_cross = [
        item
        for item in envelopes["Q06"].claim_evidence_bundles
        if item.bundle_kind == "cross_tool_observation"
    ]
    if not (
        len(q02_selection) == 1
        and q02_selection[0].support_atoms[0].evidence_ids == ["FACT-001"]
        and q02_selection[0].support_atoms[0].value == "5"
        and len(q06_cross) == 1
        and q06_cross[0].source_tool_names
        == ["analyze_time_trend", "rank_products"]
        and len(q06_cross[0].support_atoms[0].evidence_ids) == 2
    ):
        raise BundleImplementationValidationError(
            "Q02 or Q06 dependency evidence drifted"
        )
    negatives = _negative_probes(envelopes["Q02"], envelopes["Q06"])

    run_id = datetime.now().astimezone().strftime(
        "claim_evidence_bundle_v2_3_2_%Y%m%dT%H%M%S_%f%z"
    )
    parent = output_parent or PROJECT_ROOT / "results" / "raw"
    output_dir = parent / run_id
    output_dir.mkdir(parents=True, exist_ok=False)
    summary = {
        "schema_version": (
            "1.5.6-h3-claim-evidence-bundle-v2.3.2-offline-validation-v1"
        ),
        "run_id": run_id,
        "status": "passed",
        "design_audit": asdict(design_audit),
        "question_count": len(cases),
        "questions_passed": len(cases),
        "total_model_responses": total_responses,
        "total_claim_evidence_bundles": total_bundles,
        "q02_selection_limit_fact_id": "FACT-001",
        "q06_cross_tool_dependency_bundle_count": len(q06_cross),
        "negative_probes": negatives,
        "cases": cases,
        "source_hashes": {
            "design": _hash(DESIGN_PATH),
            "bundle_generator": _hash(
                PROJECT_ROOT / "src" / "claim_evidence_bundles_v2_3_2.py"
            ),
            "transport": _hash(
                PROJECT_ROOT
                / "src"
                / "deepseek_report_terminal_transport_v2_3_2.py"
            ),
            "candidate": _hash(
                PROJECT_ROOT / "src" / "online_native_tool_candidate_v2_3_2.py"
            ),
        },
        "program_authored_claim_text": False,
        "post_hoc_report_repair": False,
        "report_schema_changed": False,
        "report_validator_changed": False,
        "prompt_file_changed": False,
        "h2_or_data_changed": False,
        "real_network_opened": False,
        "real_model_called": False,
        "v2_2_3_resumed": False,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


__all__ = [
    "BundleImplementationValidationError",
    "run_offline_validation",
]
