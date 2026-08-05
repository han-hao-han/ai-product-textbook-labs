"""Run and save the formal Q02 terminal-revision implementation audit."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.q02_terminal_capacity_truncation_transport_audit_revision_implementation import (  # noqa: E402
    compile_q02_terminal_revision_implementation,
)


def main() -> int:
    result = compile_q02_terminal_revision_implementation()
    timestamp = datetime.now().astimezone().strftime(
        "%Y%m%dT%H%M%S_%f%z"
    )
    run_id = f"q02_terminal_revision_implementation_{timestamp}"
    output_dir = PROJECT_ROOT / "results" / "raw" / run_id
    summary = {
        "schema_version": "1.5.6-h3-q02-terminal-revision-implementation-v1",
        "run_id": run_id,
        "status": "passed" if result.passed else "failed",
        "execution_mode": "offline_saved_real_response_replay",
        "source_real_run_id": "q01_q10_batch_a_flash_20260803T223720_058350+0800",
        "direct_outcome_status": result.direct_outcome_status,
        "direct_error_stage": result.direct_error_stage,
        "direct_error_message": result.direct_error_message,
        "direct_tool_names": list(result.direct_tool_names),
        "direct_response_count": result.direct_response_count,
        "tool_reference_answer_status": result.tool_reference_answer_status,
        "report_content_acceptance_status": result.report_content_acceptance_status,
        "fixed_validation_issue_paths": list(
            result.fixed_validation_issue_paths
        ),
        "batch_primary_stop_stage": result.batch_primary_stop_stage,
        "batch_primary_stop_codes": list(result.batch_primary_stop_codes),
        "batch_acceptance_consequences": list(
            result.batch_acceptance_consequences
        ),
        "batch_not_evaluated_checks": list(
            result.batch_not_evaluated_checks
        ),
        "batch_program_failures": list(result.batch_program_failures),
        "batch_evaluation_states": result.batch_evaluation_states,
        "request_max_tokens": list(result.request_max_tokens),
        "offline_transport_audit": result.offline_transport_audit,
        "saved_real_transport_audit_preview": (
            result.saved_real_transport_audit_preview
        ),
        "h2_changed": False,
        "prompt_changed": False,
        "schema_changed": False,
        "acceptance_root_rules_changed": False,
        "automatic_retry_count": 0,
        "v2_2_3_resumed": False,
        "batch_b_authorized": False,
        "real_model_called": result.real_model_called,
        "network_used": result.network_used,
        "api_key_read_from_environment": result.api_key_read,
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
