"""Save the concentrated offline audit for the Q02 terminal revision."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.q02_terminal_revision_concentrated_audit import (  # noqa: E402
    Q02TerminalRevisionConcentratedAuditError,
    negative_audit_contracts,
    validate_q02_terminal_revision_implementation_contract,
)


def main() -> int:
    result = validate_q02_terminal_revision_implementation_contract()
    probes = negative_audit_contracts()
    rejected = 0
    for probe in probes:
        try:
            validate_q02_terminal_revision_implementation_contract(probe)
        except Q02TerminalRevisionConcentratedAuditError:
            rejected += 1
    timestamp = datetime.now().astimezone().strftime(
        "%Y%m%dT%H%M%S_%f%z"
    )
    run_id = f"q02_terminal_revision_concentrated_audit_{timestamp}"
    output_dir = PROJECT_ROOT / "results" / "raw" / run_id
    passed = result.passed and rejected == len(probes) == 5
    summary = {
        "schema_version": "1.5.6-h3-q02-terminal-revision-concentrated-audit-v1",
        "run_id": run_id,
        "status": "passed" if passed else "failed",
        "evidence_checks": result.evidence_checks,
        "implementation_hashes_match": result.implementation_hashes_match,
        "frozen_hashes_match": result.frozen_hashes_match,
        "q02_root_code": result.q02_root_code,
        "q01_q10_mock_passed": result.q01_q10_mock_passed,
        "q01_q10_transport_passed": result.q01_q10_transport_passed,
        "harness_negative_probes_passed": (
            result.harness_negative_probes_passed
        ),
        "batch_a_offline_status": result.batch_a_offline_status,
        "full_test_status": result.full_test_status,
        "negative_probes_passed": rejected,
        "negative_probes_total": len(probes),
        "real_model_called": False,
        "network_used": False,
        "api_key_read_from_environment": False,
        "batch_b_authorized": False,
        "v2_2_3_resumed": False,
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
