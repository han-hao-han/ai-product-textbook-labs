"""Single-use authority for the V2.3.1 concentrated real checkpoint."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from src.q01_q10_batch_a_safe_runner import (
    BATCH_A_MODEL,
    BATCH_A_QUESTION_IDS,
    BATCH_A_REQUEST_TIMEOUT_SECONDS,
    BATCH_A_RESPONSE_ATTEMPT_CAP,
    BATCH_A_TOTAL_TIMEOUT_SECONDS,
    BatchASafeRunnerError,
    ValidatedBatchAExecutionAuthority,
    validate_batch_a_runner_implementation,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT_PATH = (
    PROJECT_ROOT
    / "config"
    / "h3_batch_a_report_admissible_checkpoint_v2_3_1.json"
)
REAL_CONFIRMATION = "I_AUTHORIZE_BATCH_A_REPORT_ADMISSIBLE_V2_3_1_REAL_CALLS"


def _read() -> dict[str, Any]:
    value = json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise BatchASafeRunnerError("V2.3.1 checkpoint must be an object")
    return value


def validate_checkpoint_authority(
    *,
    confirmation: str,
    checkpoint: dict[str, Any] | None = None,
) -> ValidatedBatchAExecutionAuthority:
    validate_batch_a_runner_implementation()
    value = checkpoint or _read()
    boundary = value.get("boundary", {})
    authorization = value.get("authorization", {})
    exclusions = value.get("scope_exclusions", {})
    if confirmation != REAL_CONFIRMATION:
        raise BatchASafeRunnerError(
            "V2.3.1 exact real-call confirmation is missing"
        )
    if (
        value.get("status") != "authorized_pending_single_execution"
        or boundary.get("question_ids_in_order")
        != list(BATCH_A_QUESTION_IDS)
        or boundary.get("q02_must_pass_before_later_questions") is not True
        or boundary.get("stop_on_first_failure") is not True
        or boundary.get("model") != BATCH_A_MODEL
        or boundary.get("response_attempt_upper_bound")
        != BATCH_A_RESPONSE_ATTEMPT_CAP
        or boundary.get("automatic_retry_count") != 0
        or boundary.get("per_request_timeout_seconds")
        != BATCH_A_REQUEST_TIMEOUT_SECONDS
        or boundary.get("batch_internal_timeout_seconds")
        != BATCH_A_TOTAL_TIMEOUT_SECONDS
        or boundary.get("external_process_timeout_seconds") != 1200
        or authorization.get("authorized_by_user_current_turn") is not True
        or authorization.get("single_execution_only") is not True
        or authorization.get("consumed") is not False
        or authorization.get("real_model_calls_allowed") is not True
        or authorization.get("authorizes_batch_b") is not False
        or authorization.get("v2_2_3_resume_authorized") is not False
        or any(value is not False for value in exclusions.values())
    ):
        raise BatchASafeRunnerError(
            "V2.3.1 checkpoint is not an exact unconsumed authorization"
        )
    return ValidatedBatchAExecutionAuthority(
        mode="real_transport",
        batch_id="A",
        question_ids=BATCH_A_QUESTION_IDS,
        model=BATCH_A_MODEL,
        response_attempt_upper_bound=BATCH_A_RESPONSE_ATTEMPT_CAP,
        automatic_retry_count=0,
    )


def claim_checkpoint_authorization(run_id: str) -> dict[str, Any]:
    value = _read()
    validate_checkpoint_authority(
        confirmation=REAL_CONFIRMATION,
        checkpoint=value,
    )
    now = datetime.now().astimezone().isoformat()
    value["status"] = "execution_claimed_authorization_consumed"
    value["authorization"].update(
        {
            "consumed": True,
            "real_model_calls_allowed": False,
            "consumed_at": now,
            "consumed_run_id": run_id,
        }
    )
    CHECKPOINT_PATH.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return value


def finalize_checkpoint(
    *,
    run_id: str,
    passed: bool,
    summary_path: str,
) -> None:
    value = _read()
    authorization = value.get("authorization", {})
    if not (
        value.get("status") == "execution_claimed_authorization_consumed"
        and authorization.get("consumed") is True
        and authorization.get("consumed_run_id") == run_id
    ):
        raise BatchASafeRunnerError(
            "V2.3.1 checkpoint finalization does not match claimed run"
        )
    value["status"] = (
        "consumed_by_passed_run" if passed else "consumed_by_failed_stopped_run"
    )
    value["real_validation"] = {
        "run_id": run_id,
        "summary_path": summary_path,
        "status": (
            "passed_deterministic_pending_manual_review"
            if passed
            else "failed_stopped"
        ),
        "automatic_retry_performed": False,
        "batch_b_authorized": False,
        "v2_2_3_resumed": False,
    }
    CHECKPOINT_PATH.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


__all__ = [
    "CHECKPOINT_PATH",
    "REAL_CONFIRMATION",
    "claim_checkpoint_authorization",
    "finalize_checkpoint",
    "validate_checkpoint_authority",
]
