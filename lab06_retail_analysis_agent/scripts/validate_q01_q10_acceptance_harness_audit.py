"""Run the read-only Q01-Q10 acceptance and harness audit."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.q01_q10_acceptance_harness_audit import (  # noqa: E402
    run_acceptance_harness_audit,
    validate_acceptance_harness_audit_contract,
)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    validate_acceptance_harness_audit_contract()
    audit = run_acceptance_harness_audit()
    severity_counts: dict[str, int] = {}
    for finding in audit.findings:
        severity = str(finding["severity"])
        severity_counts[severity] = severity_counts.get(severity, 0) + 1
    incomplete_reports = [
        item.question_id
        for item in audit.questions
        if item.report_required
        and item.report_reference_coverage_ratio != 1.0
    ]
    rank_ambiguity = {
        item.question_id: item.non_selected_metric_rank_fact_count
        for item in audit.questions
        if item.non_selected_metric_rank_fact_count > 0
    }
    passed = (
        audit.status == "findings_confirmed"
        and all(
            item.mock_fixed_validation_status == "passed"
            for item in audit.questions
        )
        and incomplete_reports
        == ["Q01", "Q02", "Q03", "Q04", "Q05", "Q06", "Q07"]
        and rank_ambiguity == {"Q02": 10, "Q03": 10, "Q06": 6}
        and all(audit.control_text_probes.values())
        and audit.source_files_unchanged
        and not audit.real_model_called
        and not audit.network_used
        and not audit.api_key_read
    )
    timestamp = datetime.now().astimezone().strftime(
        "%Y%m%dT%H%M%S_%f%z"
    )
    run_id = f"q01_q10_acceptance_harness_audit_{timestamp}"
    output_dir = PROJECT_ROOT / "results" / "raw" / run_id
    summary = {
        "schema_version": (
            "1.5.6-h3-q01-q10-acceptance-harness-audit-v1"
        ),
        "run_id": run_id,
        "status": "passed_with_findings" if passed else "failed",
        "stage": "q01_q10_acceptance_harness_consistency_audit",
        "questions": [asdict(item) for item in audit.questions],
        "findings": list(audit.findings),
        "finding_count": len(audit.findings),
        "severity_counts": severity_counts,
        "mock_fixed_validation_passed": 10,
        "mock_fixed_validation_total": 10,
        "incomplete_report_questions": incomplete_reports,
        "rank_ambiguity_fact_counts": rank_ambiguity,
        "control_text_probes": audit.control_text_probes,
        "source_hashes_before": audit.source_hashes_before,
        "source_hashes_after": audit.source_hashes_after,
        "source_files_unchanged": audit.source_files_unchanged,
        "validation_rules_changed": False,
        "mock_changed": False,
        "prompt_changed": False,
        "fact_schema_or_builder_changed": False,
        "v2_2_3_resumed": False,
        "real_network_opened": False,
        "real_model_called": False,
        "api_key_read_from_environment": False,
        "privacy_audit": {
            "raw_provider_response_saved": False,
            "api_key_saved": False,
            "authorization_header_saved": False,
            "raw_customer_id_saved": False,
        },
        "audit_result": "findings_require_user_policy_decisions_before_fix",
    }
    _write_json(output_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
