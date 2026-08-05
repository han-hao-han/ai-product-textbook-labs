"""Explicit capability boundary for online and no-model experiences."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


Capability = Literal[
    "view_data_profile",
    "view_metric_contract",
    "run_manual_whitelist_tool",
    "view_structured_results",
    "view_facts_and_charts",
    "view_reference_answers",
    "import_run_record",
    "natural_language_understanding",
    "model_tool_selection",
    "autonomous_multi_tool_calls",
    "multi_turn_conversation",
    "ai_business_report",
]
OFFLINE_ALLOWED: tuple[Capability, ...] = (
    "view_data_profile",
    "view_metric_contract",
    "run_manual_whitelist_tool",
    "view_structured_results",
    "view_facts_and_charts",
    "view_reference_answers",
    "import_run_record",
)
OFFLINE_DISABLED: tuple[Capability, ...] = (
    "natural_language_understanding",
    "model_tool_selection",
    "autonomous_multi_tool_calls",
    "multi_turn_conversation",
    "ai_business_report",
)


class CapabilityDeniedError(PermissionError):
    """Raised when the active mode does not allow a capability."""


class ModePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    mode: Literal["online_agent", "offline_tool_experience"]
    user_visible_label: Literal["在线Agent", "工具层体验"]
    allowed: list[Capability]
    disabled: list[Capability]
    may_claim_agent_behavior: bool


def build_mode_policy(*, api_key_configured: bool) -> ModePolicy:
    if api_key_configured:
        return ModePolicy(
            mode="online_agent",
            user_visible_label="在线Agent",
            allowed=[*OFFLINE_ALLOWED, *OFFLINE_DISABLED],
            disabled=[],
            may_claim_agent_behavior=True,
        )
    return ModePolicy(
        mode="offline_tool_experience",
        user_visible_label="工具层体验",
        allowed=list(OFFLINE_ALLOWED),
        disabled=list(OFFLINE_DISABLED),
        may_claim_agent_behavior=False,
    )


def require_capability(
    policy: ModePolicy,
    capability: Capability,
) -> None:
    if capability not in policy.allowed:
        raise CapabilityDeniedError(
            f"{policy.user_visible_label}不支持：{capability}"
        )
