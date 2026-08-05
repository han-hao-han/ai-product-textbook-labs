"""Run and save formal evidence-guard Prompt implementation validation."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.native_report_prompt_evidence_guard_implementation import (  # noqa: E402
    validate_native_report_prompt_evidence_guard_implementation,
)


def main() -> int:
    timestamp = datetime.now().astimezone().strftime(
        "%Y%m%dT%H%M%S_%f%z"
    )
    run_id = f"native_report_prompt_evidence_guard_implementation_{timestamp}"
    output_dir = PROJECT_ROOT / "results" / "raw" / run_id
    result = validate_native_report_prompt_evidence_guard_implementation()
    summary = {
        "schema_version": "1.5.6-h3-native-report-prompt-evidence-guard-implementation-evidence-v1",
        "run_id": run_id,
        "status": "passed" if result.passed else "failed",
        "execution_mode": "offline_prompt_wiring_and_saved_response_replay",
        "prompt": {
            "version": result.prompt_version,
            "relative_path": result.prompt_relative_path,
            "predecessor_file_sha256": result.predecessor_file_sha256,
            "active_file_sha256": result.active_file_sha256,
            "active_loaded_content_sha256": result.active_loaded_content_sha256,
            "runtime_contains_all_three_guards": (
                result.runtime_prompt_contains_all_guards
            ),
        },
        "saved_q02": {
            "source_sha256": result.saved_q02_sha256,
            "status": result.saved_q02_status,
            "tool_reference_answer_status": (
                result.saved_q02_tool_reference_answer_status
            ),
            "root_failure_codes": list(result.saved_q02_root_failure_codes),
            "response_rewritten": False,
            "failure_claimed_fixed": False,
        },
        "q01_q10": {
            "statuses": result.q01_q10_statuses,
            "passed": result.q01_q10_passed,
            "total": result.q01_q10_total,
        },
        "frozen_source_hashes": result.frozen_hashes,
        "h2_changed": False,
        "data_changed": False,
        "tool_report_fact_schema_changed": False,
        "acceptance_root_rules_changed": False,
        "real_model_called": False,
        "network_used": False,
        "api_key_read_from_environment": False,
        "v2_2_3_resumed": False,
        "next_gate": "运行正式Q01至Q10全量离线入口和全量测试；不授权真实模型调用。",
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
