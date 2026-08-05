"""Single-use Q04 checkpoint with local REQUEST-value completeness."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.online_native_tool_candidate_combined_v15 import (
    COMBINED_PROMPT_VERSION,
    NativeToolOnlineCandidateCombinedV15,
)
from src.tool_routing_prompt_v1_real_runner import (
    CONSUMPTION_ROOT,
    EXPECTED_RESPONSES,
    MODEL,
    ToolRoutingAuthority,
    ToolRoutingRealRunnerError,
    ToolRoutingRunResult,
    execute_validation,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = PROJECT_ROOT / "config" / "h3_combined_prompt_v15_q04_real_validation.json"
REAL_CONFIRMATION = "I_AUTHORIZE_COMBINED_PROMPT_V15_Q04_REAL_CALLS"
QUESTION_ORDER = ("Q04",)
REPAIR_ALLOWANCE = {"Q04": 2}
RESPONSE_CAP = EXPECTED_RESPONSES["Q04"] + REPAIR_ALLOWANCE["Q04"]


def validate_real_request_v15(
    *, model: str, response_cap: int, automatic_retries: int,
    confirmation: str, consumption_root: Path = CONSUMPTION_ROOT,
) -> ToolRoutingAuthority:
    if (model, response_cap, automatic_retries) != (MODEL, RESPONSE_CAP, 0):
        raise ToolRoutingRealRunnerError(
            f"real request must be exact Flash/cap{RESPONSE_CAP}/retry0"
        )
    if confirmation != REAL_CONFIRMATION:
        raise ToolRoutingRealRunnerError("exact real confirmation is missing")
    value = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    authorization = value.get("authorization", {})
    authorization_id = authorization.get("authorization_id")
    if (
        value.get("status") != "authorized_pending_single_execution"
        or authorization.get("status") != "authorized_pending_single_execution"
        or authorization.get("real_model_calls_allowed") is not True
        or authorization.get("single_execution_only") is not True
        or authorization.get("consumed_when_first_attempt_reserved") is not True
        or not isinstance(authorization_id, str)
        or not authorization_id
    ):
        raise ToolRoutingRealRunnerError("no exact unconsumed v15 real authority")
    if (consumption_root / f"{authorization_id}.json").exists():
        raise ToolRoutingRealRunnerError("v15 real authority is already consumed")
    return ToolRoutingAuthority("real_transport", authorization_id)


def execute_validation_v15(
    *, api_key: str, registry: Any, transport_factory: Any | None,
    authority: ToolRoutingAuthority, output_parent: Path,
    run_id: str | None = None, consumption_root: Path = CONSUMPTION_ROOT,
) -> ToolRoutingRunResult:
    return execute_validation(
        api_key=api_key,
        registry=registry,
        transport_factory=transport_factory,
        authority=authority,
        output_parent=output_parent,
        run_id=run_id,
        consumption_root=consumption_root,
        candidate_type=NativeToolOnlineCandidateCombinedV15,
        prompt_version=COMBINED_PROMPT_VERSION,
        schema_namespace="combined-prompt-v15-q04",
        question_order=QUESTION_ORDER,
        continue_after_failure=True,
        response_allowance_by_question=REPAIR_ALLOWANCE,
    )


__all__ = [
    "QUESTION_ORDER", "REAL_CONFIRMATION", "REPAIR_ALLOWANCE", "RESPONSE_CAP",
    "execute_validation_v15", "validate_real_request_v15",
]
