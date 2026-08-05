"""Q04 checkpoint and Q01-Q10 full validation for combined Prompt v18."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.online_native_tool_candidate_combined_v18 import (
    COMBINED_PROMPT_VERSION, NativeToolOnlineCandidateCombinedV18,
)
from src.tool_routing_prompt_v1_real_runner import (
    CONSUMPTION_ROOT, EXPECTED_RESPONSES, MODEL, ToolRoutingAuthority,
    ToolRoutingRealRunnerError, ToolRoutingRunResult, execute_validation,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
Q04_CONTRACT_PATH = PROJECT_ROOT / "config" / "h3_combined_prompt_v18_q04_real_validation.json"
FULL_CONTRACT_PATH = PROJECT_ROOT / "config" / "h3_combined_prompt_v18_full_real_validation.json"
Q04_CONFIRMATION = "I_AUTHORIZE_COMBINED_PROMPT_V18_Q04_REAL_CALLS"
FULL_CONFIRMATION = "I_AUTHORIZE_COMBINED_PROMPT_V18_Q01_Q10_REAL_CALLS"
Q04_ORDER = ("Q04",)
FULL_ORDER = tuple(f"Q{index:02d}" for index in range(1, 11))
Q04_ALLOWANCE = {"Q04": 2}
FULL_ALLOWANCE = {item: 2 if item <= "Q07" else 0 for item in FULL_ORDER}
Q04_RESPONSE_CAP = EXPECTED_RESPONSES["Q04"] + 2
FULL_RESPONSE_CAP = sum(EXPECTED_RESPONSES.values()) + sum(FULL_ALLOWANCE.values())


def _validate(
    *, contract_path: Path, exact_confirmation: str, model: str,
    response_cap: int, exact_cap: int, automatic_retries: int,
    confirmation: str, consumption_root: Path,
) -> ToolRoutingAuthority:
    if (model, response_cap, automatic_retries) != (MODEL, exact_cap, 0):
        raise ToolRoutingRealRunnerError(f"real request must be exact Flash/cap{exact_cap}/retry0")
    if confirmation != exact_confirmation:
        raise ToolRoutingRealRunnerError("exact real confirmation is missing")
    value = json.loads(contract_path.read_text(encoding="utf-8"))
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
        raise ToolRoutingRealRunnerError("no exact unconsumed v18 authority")
    if (consumption_root / f"{authorization_id}.json").exists():
        raise ToolRoutingRealRunnerError("v18 authority is already consumed")
    return ToolRoutingAuthority("real_transport", authorization_id)


def validate_real_request_v18_q04(**kwargs: Any) -> ToolRoutingAuthority:
    return _validate(
        contract_path=Q04_CONTRACT_PATH, exact_confirmation=Q04_CONFIRMATION,
        exact_cap=Q04_RESPONSE_CAP, consumption_root=kwargs.pop("consumption_root", CONSUMPTION_ROOT),
        **kwargs,
    )


def validate_real_request_v18_full(**kwargs: Any) -> ToolRoutingAuthority:
    return _validate(
        contract_path=FULL_CONTRACT_PATH, exact_confirmation=FULL_CONFIRMATION,
        exact_cap=FULL_RESPONSE_CAP, consumption_root=kwargs.pop("consumption_root", CONSUMPTION_ROOT),
        **kwargs,
    )


def _execute(
    *, question_order: tuple[str, ...], allowance: dict[str, int], namespace: str,
    api_key: str, registry: Any, transport_factory: Any | None,
    authority: ToolRoutingAuthority, output_parent: Path, run_id: str | None,
    consumption_root: Path,
) -> ToolRoutingRunResult:
    return execute_validation(
        api_key=api_key, registry=registry, transport_factory=transport_factory,
        authority=authority, output_parent=output_parent, run_id=run_id,
        consumption_root=consumption_root,
        candidate_type=NativeToolOnlineCandidateCombinedV18,
        prompt_version=COMBINED_PROMPT_VERSION, schema_namespace=namespace,
        question_order=question_order, continue_after_failure=True,
        response_allowance_by_question=allowance,
    )


def execute_validation_v18_q04(*, run_id: str | None = None, consumption_root: Path = CONSUMPTION_ROOT, **kwargs: Any) -> ToolRoutingRunResult:
    return _execute(question_order=Q04_ORDER, allowance=Q04_ALLOWANCE,
                    namespace="combined-prompt-v18-q04", run_id=run_id,
                    consumption_root=consumption_root, **kwargs)


def execute_validation_v18_full(*, run_id: str | None = None, consumption_root: Path = CONSUMPTION_ROOT, **kwargs: Any) -> ToolRoutingRunResult:
    return _execute(question_order=FULL_ORDER, allowance=FULL_ALLOWANCE,
                    namespace="combined-prompt-v18-full", run_id=run_id,
                    consumption_root=consumption_root, **kwargs)


__all__ = [
    "FULL_ORDER", "FULL_RESPONSE_CAP", "Q04_ORDER", "Q04_RESPONSE_CAP",
    "execute_validation_v18_full", "execute_validation_v18_q04",
    "validate_real_request_v18_full", "validate_real_request_v18_q04",
]
