"""Save offline evidence for the Q01-Q10 new-Harness Flash plan."""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.q01_q10_new_harness_flash_real_validation_plan import (  # noqa: E402
    Q01Q10NewHarnessFlashPlanError,
    load_q01_q10_new_harness_flash_plan,
    validate_q01_q10_new_harness_flash_plan,
)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _probe(mutator: Callable[[dict[str, Any]], None]) -> bool:
    changed = deepcopy(load_q01_q10_new_harness_flash_plan())
    mutator(changed)
    try:
        validate_q01_q10_new_harness_flash_plan(changed)
    except Q01Q10NewHarnessFlashPlanError:
        return True
    return False


def main() -> int:
    preflight = validate_q01_q10_new_harness_flash_plan()
    probes = {
        "model_drift_rejected": _probe(
            lambda plan: plan["scope"].update({"model": "deepseek-v4-pro"})
        ),
        "batch_a_scope_drift_rejected": _probe(
            lambda plan: plan["batches"][0]["question_ids_in_order"].append("Q01")
        ),
        "batch_a_ninth_attempt_rejected": _probe(
            lambda plan: plan["batches"][0].update({"maximum_response_attempts": 9})
        ),
        "batch_b_thirteenth_attempt_rejected": _probe(
            lambda plan: plan["batches"][1].update({"maximum_response_attempts": 13})
        ),
        "total_twenty_first_attempt_rejected": _probe(
            lambda plan: plan["response_arithmetic"].update({"all_questions_maximum_response_attempts": 21})
        ),
        "automatic_retry_rejected": _probe(
            lambda plan: plan["failure_and_stop_rules"].update({"automatic_retry_count": 1})
        ),
        "continue_after_transport_failure_rejected": _probe(
            lambda plan: plan["failure_and_stop_rules"].update({"stop_current_batch_on_first_transport_failure": False})
        ),
        "automatic_network_resume_rejected": _probe(
            lambda plan: plan["failure_and_stop_rules"].update({"automatic_resume_after_network_recovery": True})
        ),
        "batch_b_inherited_authority_rejected": _probe(
            lambda plan: plan["authorization"].update({"batch_a_authorization_does_not_authorize_batch_b": False})
        ),
        "protocol_only_acceptance_rejected": _probe(
            lambda plan: plan["deterministic_acceptance"].update({"protocol_and_dataflow_passed_is_real_success": True})
        ),
        "automatic_manual_pass_rejected": _probe(
            lambda plan: plan["manual_review"].update({"fully_accepted_label_may_be_set_automatically": True})
        ),
        "v2_2_3_resume_rejected": _probe(
            lambda plan: plan["scope"].update({"v2_2_3_resumed": True})
        ),
        "premature_real_runner_rejected": _probe(
            lambda plan: plan["implementation"].update({"guarded_real_runner": "scripts/run_real.py"})
        ),
        "frozen_batch_a_cap_drift_rejected": _probe(
            lambda plan: plan["user_freeze"].update({"batch_a_response_attempt_upper_bound": 9})
        ),
        "frozen_record_authority_grant_rejected": _probe(
            lambda plan: plan["user_freeze"].update({"freeze_does_not_authorize_real_calls": False})
        ),
    }
    passed = all(probes.values())
    timestamp = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S_%f%z")
    run_id = f"q01_q10_new_harness_flash_plan_offline_{timestamp}"
    output_dir = PROJECT_ROOT / "results" / "raw" / run_id
    summary = {
        "schema_version": "1.5.6-h3-q01-q10-new-harness-flash-plan-offline-v1",
        "run_id": run_id,
        "status": "passed" if passed else "failed",
        "model": preflight.model,
        "batch_a_question_ids": list(preflight.batch_a_question_ids),
        "batch_b_question_ids": list(preflight.batch_b_question_ids),
        "batch_a_attempt_cap": preflight.batch_a_attempt_cap,
        "batch_b_attempt_cap": preflight.batch_b_attempt_cap,
        "total_attempt_cap": preflight.total_attempt_cap,
        "automatic_retry_count": preflight.automatic_retry_count,
        "real_model_calls_allowed": preflight.real_model_calls_allowed,
        "guarded_runner_ready": preflight.guarded_runner_ready,
        "checks": list(preflight.checks),
        "negative_probes": probes,
        "real_network_opened": False,
        "real_model_called": False,
        "api_key_read_from_environment": False,
        "privacy_audit": {
            "api_key_saved": False,
            "authorization_header_saved": False,
            "request_headers_saved": False,
            "request_body_saved": False,
            "raw_customer_id_exported": False,
            "raw_retail_rows_exported": False,
            "local_absolute_paths_saved": False
        }
    }
    _write_json(output_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
