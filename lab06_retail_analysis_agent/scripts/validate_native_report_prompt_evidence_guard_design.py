"""Validate and save the native report Prompt evidence-guard design."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.native_report_prompt_evidence_guard_design import (  # noqa: E402
    validate_native_report_prompt_evidence_guard_design,
)


def main() -> int:
    timestamp = datetime.now().astimezone().strftime(
        "%Y%m%dT%H%M%S_%f%z"
    )
    run_id = f"native_report_prompt_evidence_guard_design_{timestamp}"
    output_dir = PROJECT_ROOT / "results" / "raw" / run_id
    result = validate_native_report_prompt_evidence_guard_design()
    summary = {
        "schema_version": "1.5.6-h3-native-report-prompt-evidence-guard-design-evidence-v1",
        "run_id": run_id,
        "status": "passed" if result.passed else "failed",
        "execution_mode": "offline_design_validation",
        "active_prompt_sha256": result.active_prompt_sha256,
        "saved_q02_response_sha256": result.saved_response_sha256,
        "targeted_root_issue_count": result.targeted_root_issue_count,
        "root_issue_count": result.root_issue_count,
        "rule_ids": list(result.rule_ids),
        "q01_q10_offline_status": result.q01_q10_offline_status,
        "negative_probes": result.negative_probes,
        "prompt_changed": False,
        "validator_changed": False,
        "real_model_called": False,
        "network_used": False,
        "api_key_read_from_environment": False,
        "v2_2_3_resumed": False,
        "candidate_does_not_claim_real_improvement": True,
        "next_gate": (
            "用户决定是否冻结并授权创建新版本报告Prompt；"
            "冻结本身不授权实施或真实调用。"
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
