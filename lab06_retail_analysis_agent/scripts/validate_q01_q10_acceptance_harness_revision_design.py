"""Validate and preserve evidence for the offline six-boundary design."""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.q01_q10_acceptance_harness_revision_design import (  # noqa: E402
    AcceptanceHarnessRevisionDesignError,
    compile_revision_design_preview,
    load_acceptance_harness_revision_design,
    validate_acceptance_harness_revision_design,
)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _negative_probes() -> dict[str, bool]:
    base = load_acceptance_harness_revision_design()
    candidates: dict[str, dict[str, Any]] = {}

    implementation = deepcopy(base)
    implementation["authorization"]["implementation_allowed"] = True
    candidates["implementation_authority_rejected"] = implementation

    h2_change = deepcopy(base)
    h2_change["scope"]["h2_reference_answers_changed"] = True
    candidates["h2_reference_change_rejected"] = h2_change

    resume = deepcopy(base)
    resume["scope"]["v2_2_3_resumed"] = True
    candidates["v2_2_3_resume_rejected"] = resume

    real_call = deepcopy(base)
    real_call["scope"]["real_model_calls_allowed"] = True
    candidates["real_model_authority_rejected"] = real_call

    rank = deepcopy(base)
    rank["boundary_3_rank_semantics"]["selected_route"] = (
        "copy_row_rank_to_all_metrics"
    )
    candidates["rank_route_drift_rejected"] = rank

    provenance = deepcopy(base)
    provenance["boundary_2_provenance"]["source_types"].pop("REQUEST")
    candidates["provenance_union_weakening_rejected"] = provenance

    semantic = deepcopy(base)
    semantic["boundary_4_semantic_rules"][
        "plain_significant_is_not_statistical_hard_fail"
    ] = False
    candidates["plain_significant_hard_fail_rejected"] = semantic

    mock = deepcopy(base)
    mock["boundary_5_mock_responsibility"][
        "current_generic_mock_report_may_pass_content_acceptance"
    ] = True
    candidates["generic_mock_content_pass_rejected"] = mock

    q10 = deepcopy(base)
    q10["boundary_6_control_content"]["Q10"][
        "future_control_schema_addition"
    ]["enum_values"] = ["forecasting_unsupported"]
    candidates["q10_boundary_code_weakening_rejected"] = q10

    result: dict[str, bool] = {}
    for name, candidate in candidates.items():
        try:
            validate_acceptance_harness_revision_design(candidate)
        except AcceptanceHarnessRevisionDesignError:
            result[name] = True
        else:
            result[name] = False
    return result


def main() -> int:
    validate_acceptance_harness_revision_design()
    preview = compile_revision_design_preview()
    probes = _negative_probes()
    passed = (
        preview.status == "design_consistent_no_implementation"
        and preview.manifest_leaf_counts
        == {
            "Q01": 7,
            "Q02": 27,
            "Q03": 23,
            "Q04": 7,
            "Q05": 14,
            "Q06": 20,
            "Q07": 12,
        }
        and preview.current_ambiguous_rank_counts
        == {"Q02": 10, "Q03": 10, "Q06": 6}
        and preview.source_files_unchanged
        and not preview.implementation_performed
        and not preview.real_model_called
        and not preview.network_used
        and not preview.api_key_read
        and all(probes.values())
    )
    timestamp = datetime.now().astimezone().strftime(
        "%Y%m%dT%H%M%S_%f%z"
    )
    run_id = (
        "q01_q10_acceptance_harness_revision_design_" + timestamp
    )
    output_dir = PROJECT_ROOT / "results" / "raw" / run_id
    summary = {
        "schema_version": (
            "1.5.6-h3-q01-q10-acceptance-harness-revision-design-v1"
        ),
        "run_id": run_id,
        "status": "passed" if passed else "failed",
        "stage": "q01_q10_acceptance_harness_revision_offline_design",
        "candidate_result": "design_ready_not_implemented",
        "preview": asdict(preview),
        "negative_probes": probes,
        "negative_probe_passed": sum(probes.values()),
        "negative_probe_total": len(probes),
        "six_boundaries": [
            "report_completeness",
            "request_and_policy_provenance",
            "rank_semantics",
            "semantic_hard_rule_vs_manual_review",
            "mock_responsibility_and_status_naming",
            "clarification_and_refusal_content",
        ],
        "h2_reference_answers_changed": False,
        "v2_2_3_resumed": False,
        "current_harness_implementation_changed": False,
        "real_network_opened": False,
        "real_model_called": False,
        "api_key_read_from_environment": False,
        "privacy_audit": {
            "raw_provider_response_saved": False,
            "api_key_saved": False,
            "authorization_header_saved": False,
            "raw_customer_id_saved": False,
        },
        "next_gate": (
            "等待用户冻结六项修订设计；冻结本身不授权实现或真实调用"
        ),
    }
    _write_json(output_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
