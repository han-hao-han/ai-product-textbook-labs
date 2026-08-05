"""Save formal offline evidence for the Q02 failure/Harness design."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.q02_failure_harness_revision_design import (  # noqa: E402
    EXPECTED_ROOT_CODES,
    compile_q02_failure_harness_design_preview,
    validate_q02_failure_harness_revision_design,
)


def main() -> int:
    contract = validate_q02_failure_harness_revision_design()
    preview = compile_q02_failure_harness_design_preview()
    timestamp = datetime.now().astimezone().strftime(
        "%Y%m%dT%H%M%S_%f%z"
    )
    run_id = f"q02_failure_harness_revision_design_{timestamp}"
    output_dir = PROJECT_ROOT / "results" / "raw" / run_id
    passed = (
        list(preview.root_failure_codes) == EXPECTED_ROOT_CODES
        and (preview.current_manifest_total, preview.current_manifest_covered)
        == (27, 0)
        and (preview.retained_manifest_total, preview.retained_manifest_covered)
        == (27, 26)
        and (preview.candidate_manifest_total, preview.candidate_manifest_covered)
        == (27, 27)
        and preview.candidate_metric_mapping_covered
        and preview.saved_chart_requests == 1
        and preview.buildable_saved_charts == 1
        and preview.current_stop_reason == "unexpected_terminal_status"
        and preview.candidate_primary_stop_stage == "report_validation"
        and preview.source_files_unchanged
        and not preview.implementation_performed
        and not preview.real_model_called
        and not preview.network_used
        and not preview.api_key_read
        and contract["scope"]["offline_design_only"] is True
    )
    summary = {
        "schema_version": "1.5.6-h3-q02-failure-harness-revision-design-validation-v1",
        "run_id": run_id,
        "status": "passed" if passed else "failed",
        "candidate_result": "design_ready_not_implemented",
        "source_real_run_id": contract["prerequisite"]["real_run_id"],
        "root_failure_codes": list(preview.root_failure_codes),
        "current_manifest": {
            "total": preview.current_manifest_total,
            "covered": preview.current_manifest_covered,
        },
        "retained_manifest": {
            "total": preview.retained_manifest_total,
            "covered": preview.retained_manifest_covered,
        },
        "candidate_manifest": {
            "total": preview.candidate_manifest_total,
            "covered": preview.candidate_manifest_covered,
        },
        "candidate_metric_mapping_covered": (
            preview.candidate_metric_mapping_covered
        ),
        "saved_chart_request_count": preview.saved_chart_requests,
        "buildable_saved_chart_count": preview.buildable_saved_charts,
        "current_stop_reason": preview.current_stop_reason,
        "candidate_primary_stop_stage": (
            preview.candidate_primary_stop_stage
        ),
        "source_files_unchanged": preview.source_files_unchanged,
        "implementation_performed": preview.implementation_performed,
        "h2_reference_answers_changed": False,
        "prompt_changed": False,
        "report_validation_rules_changed": False,
        "average_value_rule_changed": False,
        "analysis_scope_row_count_rule_changed": False,
        "v2_2_3_resumed": False,
        "real_model_called": preview.real_model_called,
        "network_used": preview.network_used,
        "api_key_read_from_environment": preview.api_key_read,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
