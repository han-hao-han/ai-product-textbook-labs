"""Q01/Q06 checkpoint and Q01-Q10 full validation for v20."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.online_native_tool_candidate_combined_v20 import (
    COMBINED_PROMPT_VERSION, NativeToolOnlineCandidateCombinedV20,
)
from src.tool_routing_prompt_v1_real_runner import (
    CONSUMPTION_ROOT, EXPECTED_RESPONSES, MODEL, ToolRoutingAuthority,
    ToolRoutingRealRunnerError, ToolRoutingRunResult, execute_validation,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT_CONTRACT = PROJECT_ROOT / "config" / "h3_combined_prompt_v20_q01_q06_real_validation.json"
FULL_CONTRACT = PROJECT_ROOT / "config" / "h3_combined_prompt_v20_full_real_validation.json"
CHECKPOINT_CONFIRMATION = "I_AUTHORIZE_COMBINED_PROMPT_V20_Q01_Q06_REAL_CALLS"
FULL_CONFIRMATION = "I_AUTHORIZE_COMBINED_PROMPT_V20_Q01_Q10_REAL_CALLS"
CHECKPOINT_ORDER = ("Q01", "Q06")
FULL_ORDER = tuple(f"Q{index:02d}" for index in range(1, 11))
CHECKPOINT_ALLOWANCE = {item: 2 for item in CHECKPOINT_ORDER}
FULL_ALLOWANCE = {item: 2 if item <= "Q07" else 0 for item in FULL_ORDER}
CHECKPOINT_CAP = sum(EXPECTED_RESPONSES[item] + 2 for item in CHECKPOINT_ORDER)
FULL_CAP = sum(EXPECTED_RESPONSES.values()) + sum(FULL_ALLOWANCE.values())


def _validate(contract: Path, exact_confirmation: str, exact_cap: int, *, model: str,
              response_cap: int, automatic_retries: int, confirmation: str,
              consumption_root: Path = CONSUMPTION_ROOT) -> ToolRoutingAuthority:
    if (model, response_cap, automatic_retries) != (MODEL, exact_cap, 0):
        raise ToolRoutingRealRunnerError(f"real request must be exact Flash/cap{exact_cap}/retry0")
    if confirmation != exact_confirmation:
        raise ToolRoutingRealRunnerError("exact real confirmation is missing")
    value = json.loads(contract.read_text(encoding="utf-8"))
    authorization = value.get("authorization", {})
    authorization_id = authorization.get("authorization_id")
    if (
        value.get("status") != "authorized_pending_single_execution"
        or authorization.get("status") != "authorized_pending_single_execution"
        or authorization.get("real_model_calls_allowed") is not True
        or authorization.get("single_execution_only") is not True
        or authorization.get("consumed_when_first_attempt_reserved") is not True
        or not isinstance(authorization_id, str) or not authorization_id
    ):
        raise ToolRoutingRealRunnerError("no exact unconsumed v20 authority")
    if (consumption_root / f"{authorization_id}.json").exists():
        raise ToolRoutingRealRunnerError("v20 authority is already consumed")
    return ToolRoutingAuthority("real_transport", authorization_id)


def validate_real_request_v20_checkpoint(**kwargs: Any) -> ToolRoutingAuthority:
    return _validate(CHECKPOINT_CONTRACT, CHECKPOINT_CONFIRMATION, CHECKPOINT_CAP, **kwargs)


def validate_real_request_v20_full(**kwargs: Any) -> ToolRoutingAuthority:
    return _validate(FULL_CONTRACT, FULL_CONFIRMATION, FULL_CAP, **kwargs)


def _execute(order: tuple[str, ...], allowance: dict[str, int], namespace: str, **kwargs: Any) -> ToolRoutingRunResult:
    return execute_validation(
        candidate_type=NativeToolOnlineCandidateCombinedV20,
        prompt_version=COMBINED_PROMPT_VERSION, schema_namespace=namespace,
        question_order=order, continue_after_failure=True,
        response_allowance_by_question=allowance, **kwargs,
    )


def execute_validation_v20_checkpoint(**kwargs: Any) -> ToolRoutingRunResult:
    return _execute(CHECKPOINT_ORDER, CHECKPOINT_ALLOWANCE, "combined-prompt-v20-q01-q06", **kwargs)


def execute_validation_v20_full(**kwargs: Any) -> ToolRoutingRunResult:
    return _execute(FULL_ORDER, FULL_ALLOWANCE, "combined-prompt-v20-full", **kwargs)


__all__ = [
    "CHECKPOINT_CAP", "FULL_CAP", "execute_validation_v20_checkpoint",
    "execute_validation_v20_full", "validate_real_request_v20_checkpoint",
    "validate_real_request_v20_full",
]
