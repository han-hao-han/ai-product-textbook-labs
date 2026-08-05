"""Save offline evidence for the six-boundary harness implementation."""

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

from src.acceptance_harness_offline_validation import (  # noqa: E402
    AcceptanceHarnessImplementationError,
    EXPECTED_GENERIC,
    EXPECTED_MANIFEST_COUNTS,
    load_acceptance_harness_implementation,
    run_acceptance_harness_implementation_verification,
    validate_acceptance_harness_implementation,
)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _negative_probes() -> dict[str, bool]:
    base = load_acceptance_harness_implementation()
    candidates: dict[str, dict[str, Any]] = {}
    fields = (
        ("h2_change", "scope", "h2_reference_answers_changed"),
        ("prompt_change", "scope", "prompt_changed"),
        ("tool_schema_change", "scope", "tool_names_or_argument_schemas_changed"),
        ("v2_2_3_resume", "scope", "v2_2_3_resumed"),
        ("real_call", "scope", "real_model_calls_allowed"),
    )
    for name, section, field in fields:
        changed = deepcopy(base)
        changed[section][field] = True
        candidates[f"{name}_rejected"] = changed
    provenance = deepcopy(base)
    provenance["implementation"]["report_evidence_source_types"] = ["FACT"]
    candidates["provenance_weakening_rejected"] = provenance
    rank = deepcopy(base)
    rank["implementation"]["rank_route"] = "copy_row_rank_to_all_metrics"
    candidates["rank_drift_rejected"] = rank
    semantics = deepcopy(base)
    semantics["implementation"]["plain_significant_route"] = "hard_fail"
    candidates["semantic_drift_rejected"] = semantics
    codes = deepcopy(base)
    codes["implementation"]["q10_boundary_codes"] = [
        "forecasting_unsupported"
    ]
    candidates["q10_code_weakening_rejected"] = codes

    result = {}
    for name, candidate in candidates.items():
        try:
            validate_acceptance_harness_implementation(candidate)
        except AcceptanceHarnessImplementationError:
            result[name] = True
        else:
            result[name] = False
    return result


def main() -> int:
    verification = run_acceptance_harness_implementation_verification()
    probes = _negative_probes()
    passed = (
        verification.generic_mock_statuses == EXPECTED_GENERIC
        and verification.complete_fixture_statuses
        == {
            f"Q{index:02d}": "passed_deterministic_pending_manual_review"
            for index in range(1, 8)
        }
        and verification.manifest_counts == EXPECTED_MANIFEST_COUNTS
        and verification.manifest_all_covered
        and verification.current_non_selected_metric_rank_counts
        == {"Q02": 0, "Q03": 0, "Q06": 0}
        and verification.q09_wrong_alternative_status == "failed"
        and verification.q10_contradictory_status == "failed"
        and verification.source_files_unchanged_during_verification
        and not verification.h2_reference_answers_changed
        and not verification.v2_2_3_resumed
        and not verification.real_model_called
        and not verification.network_used
        and not verification.api_key_read
        and all(probes.values())
    )
    timestamp = datetime.now().astimezone().strftime(
        "%Y%m%dT%H%M%S_%f%z"
    )
    run_id = f"acceptance_harness_six_boundary_implementation_{timestamp}"
    output_dir = PROJECT_ROOT / "results" / "raw" / run_id
    summary = {
        "schema_version": "1.5.6-h3-acceptance-harness-six-boundary-implementation-evidence-v1",
        "run_id": run_id,
        "status": "passed" if passed else "failed",
        "stage": "q01_q10_acceptance_harness_six_boundary_offline_implementation",
        "verification": asdict(verification),
        "negative_probes": probes,
        "negative_probe_passed": sum(probes.values()),
        "negative_probe_total": len(probes),
        "h2_reference_answers_changed": False,
        "v2_2_3_resumed": False,
        "real_model_called": False,
        "network_used": False,
        "api_key_read": False,
        "privacy_audit": {
            "raw_provider_response_saved": False,
            "api_key_saved": False,
            "authorization_header_saved": False,
            "raw_customer_id_saved": False
        },
        "next_gate": "用户审阅离线实现；真实模型验证仍需单独设计和授权"
    }
    _write_json(output_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
