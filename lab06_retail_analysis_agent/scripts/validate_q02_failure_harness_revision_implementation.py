"""Run and save the formal Q02 saved-response implementation audit."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.q02_failure_harness_revision_implementation import (  # noqa: E402
    ROOT_CODES,
    run_q02_implementation_validation,
)


def main() -> int:
    timestamp = datetime.now().astimezone().strftime(
        "%Y%m%dT%H%M%S_%f%z"
    )
    run_id = f"q02_failure_harness_implementation_{timestamp}"
    output_dir = PROJECT_ROOT / "results" / "raw" / run_id
    result = run_q02_implementation_validation(
        output_parent=output_dir,
        batch_run_id="saved_q02_batch_regression",
    )
    case = result.case
    manifest = case["new_harness_validation"]["evidence_manifest"]
    summary = {
        "schema_version": "1.5.6-h3-q02-failure-harness-implementation-validation-v1",
        "run_id": run_id,
        "status": "passed" if result.passed else "failed",
        "execution_mode": "offline_saved_real_response_replay",
        "source_real_run_id": "q01_q10_batch_a_flash_20260803T195956_363133+0800",
        "batch_evidence_path": f"results/raw/{run_id}/saved_q02_batch_regression/summary.json",
        "q02_evidence_path": f"results/raw/{run_id}/saved_q02_batch_regression/Q02.json",
        "q02_status": case["program_status"],
        "root_failure_codes": result.batch_summary["primary_stop_codes"],
        "root_failure_codes_unchanged": (
            result.batch_summary["primary_stop_codes"] == ROOT_CODES
        ),
        "formal_report_is_empty": (
            case["outcome"]["report_draft"] is None
            and case["outcome"]["report_validation"] is None
        ),
        "rejected_report_publishable": case["outcome"][
            "rejected_report_evidence"
        ]["publishable"],
        "report_completeness_status": case["evaluation_states"][
            "report_completeness"
        ],
        "chart_acceptance_status": case["evaluation_states"][
            "chart_acceptance"
        ],
        "diagnostic_manifest": {
            "total": len(manifest),
            "covered": sum(bool(item["covered"]) for item in manifest),
        },
        "primary_stop_stage": result.batch_summary["primary_stop_stage"],
        "stop_reason": result.batch_summary["stop_reason"],
        "q02_chart_count_mismatch_present": (
            "q02_chart_count_mismatch" in case["program_failures"]
        ),
        "frozen_sources_unchanged": (
            result.frozen_hashes_before == result.frozen_hashes_after
        ),
        "real_model_called": False,
        "network_used": False,
        "api_key_read_from_environment": False,
        "v2_2_3_resumed": False,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
