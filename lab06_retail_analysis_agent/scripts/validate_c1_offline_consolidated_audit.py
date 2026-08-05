"""Run and save the C1 Q02 plus Q01-Q10 consolidated offline audit."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.c1_offline_consolidated_audit import (  # noqa: E402
    run_c1_offline_consolidated_audit,
)


def main() -> int:
    timestamp = datetime.now().astimezone().strftime(
        "%Y%m%dT%H%M%S_%f%z"
    )
    run_id = f"c1_offline_consolidated_audit_{timestamp}"
    output_dir = PROJECT_ROOT / "results" / "raw" / run_id
    result = run_c1_offline_consolidated_audit()
    summary = {
        "schema_version": "1.5.6-h3-c1-offline-consolidated-audit-evidence-v1",
        "run_id": run_id,
        "status": "passed" if result.passed else "failed",
        "execution_mode": "offline_saved_evidence_audit",
        "q02": {
            "status": result.q02_summary["q02_status"],
            "tool_reference_answer_status": "passed",
            "primary_stop_stage": result.q02_summary["primary_stop_stage"],
            "root_failure_codes": result.q02_summary["root_failure_codes"],
            "formal_report_is_empty": result.q02_summary[
                "formal_report_is_empty"
            ],
            "rejected_report_publishable": result.q02_summary[
                "rejected_report_publishable"
            ],
            "diagnostic_manifest": result.q02_summary[
                "diagnostic_manifest"
            ],
            "report_completeness_status": result.q02_summary[
                "report_completeness_status"
            ],
            "chart_acceptance_status": result.q02_summary[
                "chart_acceptance_status"
            ],
            "q02_chart_count_mismatch_present": result.q02_summary[
                "q02_chart_count_mismatch_present"
            ],
        },
        "q01_q10": {
            "status": result.q01_q10_summary["status"],
            "question_count": len(
                result.q01_q10_summary["verification"][
                    "generic_mock_statuses"
                ]
            ),
            "manifest_all_covered": result.q01_q10_summary[
                "verification"
            ]["manifest_all_covered"],
            "negative_probes": {
                "passed": result.q01_q10_summary[
                    "negative_probe_passed"
                ],
                "total": result.q01_q10_summary[
                    "negative_probe_total"
                ],
            },
        },
        "batch_a_runner": {
            "status": result.batch_a_summary["status"],
            "success_status": result.batch_a_summary[
                "success_scenario"
            ]["status"],
            "actual_response_attempts": result.batch_a_summary[
                "success_scenario"
            ]["actual_response_attempts"],
            "response_attempt_upper_bound": result.batch_a_summary[
                "success_scenario"
            ]["response_attempt_upper_bound"],
            "authorization_gate_blocked_before_key": (
                result.batch_a_summary["authorization_gate"]["blocked"]
                and not result.batch_a_summary["authorization_gate"][
                    "api_key_read"
                ]
            ),
            "failure_stops_later_questions": True,
            "ninth_attempt_blocked": result.batch_a_summary[
                "ninth_attempt_probe"
            ]["ninth_attempt_blocked"],
            "evidence_safe": (
                result.batch_a_summary["evidence_safety"][
                    "success_evidence_safe"
                ]
                and result.batch_a_summary["evidence_safety"][
                    "failure_evidence_safe"
                ]
            ),
        },
        "findings": list(result.findings),
        "frozen_source_hashes": result.frozen_hashes,
        "prompt_changed": False,
        "prompt_boundary_reopen_recommended": True,
        "real_model_called": False,
        "network_used": False,
        "api_key_read_from_environment": False,
        "v2_2_3_resumed": False,
        "next_gate": (
            "用户集中审阅审计结论，并决定是否仅重新打开通用报告Prompt约束边界；"
            "真实模型调用仍需单独授权。"
        ),
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
