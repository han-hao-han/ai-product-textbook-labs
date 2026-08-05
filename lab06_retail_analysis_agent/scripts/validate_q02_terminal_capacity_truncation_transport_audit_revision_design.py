"""Save formal offline evidence for the Q02 terminal revision design."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.q02_terminal_capacity_truncation_transport_audit_revision_design import (  # noqa: E402
    Q02TerminalRevisionDesignError,
    compile_q02_terminal_revision_preview,
    negative_probe_contracts,
    validate_q02_terminal_revision_design,
)


def main() -> int:
    contract = validate_q02_terminal_revision_design()
    preview = compile_q02_terminal_revision_preview()
    implementation_completed = contract["status"] == (
        "frozen_by_user_offline_implementation_completed"
    )
    probes = negative_probe_contracts()
    rejected = 0
    for probe in probes:
        try:
            validate_q02_terminal_revision_design(probe)
        except Q02TerminalRevisionDesignError:
            rejected += 1

    timestamp = datetime.now().astimezone().strftime(
        "%Y%m%dT%H%M%S_%f%z"
    )
    run_id = f"q02_terminal_revision_design_{timestamp}"
    output_dir = PROJECT_ROOT / "results" / "raw" / run_id
    passed = (
        preview.passed
        and preview.observed_finish_reason == "length"
        and preview.observed_completion_tokens == 4096
        and preview.proposed_report_terminal_max_tokens == 8192
        and preview.proposed_primary_stop_code == "terminal_output_truncated"
        and preview.proposed_transport_mode == "real_transport"
        and preview.response_counts
        == {
            "attempted": 2,
            "http_responses_received": 2,
            "parsed_responses": 2,
            "failed_attempts": 0,
        }
        and rejected == len(probes) == 9
        and preview.source_files_unchanged
        and preview.implementation_performed is implementation_completed
        and not preview.real_model_called
        and not preview.network_used
        and not preview.api_key_read
        and contract["scope"]["offline_design_only"] is True
    )
    summary = {
        "schema_version": "1.5.6-h3-q02-terminal-revision-design-validation-v1",
        "run_id": run_id,
        "status": "passed" if passed else "failed",
        "candidate_result": (
            "frozen_design_implemented_offline"
            if implementation_completed
            else "design_ready_not_implemented"
        ),
        "source_real_run_id": contract["source_evidence"]["run_id"],
        "observed_finish_reason": preview.observed_finish_reason,
        "observed_completion_tokens": preview.observed_completion_tokens,
        "observed_terminal_content_characters": (
            preview.observed_content_characters
        ),
        "proposed_capacity_policy": {
            "nonterminal_tool_selection_max_tokens": 4096,
            "report_terminal_max_tokens": (
                preview.proposed_report_terminal_max_tokens
            ),
            "clarification_or_boundary_terminal_max_tokens": 4096,
        },
        "proposed_primary_stop_stage": "model_response",
        "proposed_primary_stop_code": preview.proposed_primary_stop_code,
        "proposed_not_evaluated_checks": list(
            preview.proposed_not_evaluated_checks
        ),
        "proposed_transport_mode": preview.proposed_transport_mode,
        "response_counts": preview.response_counts,
        "negative_probes_passed": rejected,
        "negative_probes_total": len(probes),
        "source_files_unchanged": preview.source_files_unchanged,
        "implementation_performed": preview.implementation_performed,
        "h2_changed": False,
        "prompt_changed": False,
        "schema_changed": False,
        "acceptance_root_rules_changed": False,
        "v2_2_3_resumed": False,
        "batch_b_authorized": False,
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
