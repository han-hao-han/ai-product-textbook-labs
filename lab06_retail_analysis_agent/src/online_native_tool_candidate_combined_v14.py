"""Combined v13 with bounded terminal Schema and semantic feedback."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from src.online_native_tool_candidate_combined_v13 import (
    NativeToolOnlineCandidateCombinedV13,
)
from src.online_native_tool_candidate_v2_1_revision import (
    MAX_RESPONSES_PER_FIXED_QUESTION,
    NATIVE_REAL_MODEL_CONFIRMATION,
)
from src.terminal_protocol_feedback_v14 import (
    load_protocol_validation_feedback_prompt_v14,
    terminal_protocol_issues_v14,
)


COMBINED_PROMPT_VERSION = (
    "1.5.6-h3-native-tool-routing-v3-report-v5-claim-groups-v10-"
    "atom-required-v11-slot2-literal-v12-feedback-v13-protocol-v14"
)


def validate_combined_v14_real_authorization(
    *,
    confirmation: str,
    approved_model_responses: int,
    question_count: int,
) -> None:
    """Keep V14's two report-correction responses local to this candidate."""

    if confirmation != NATIVE_REAL_MODEL_CONFIRMATION:
        raise ValueError("native real-model confirmation is missing")
    if (
        isinstance(approved_model_responses, bool)
        or not isinstance(approved_model_responses, int)
        or approved_model_responses <= 0
    ):
        raise ValueError("approved model responses must be a positive integer")
    if (
        isinstance(question_count, bool)
        or not isinstance(question_count, int)
        or question_count <= 0
    ):
        raise ValueError("question count must be a positive integer")
    maximum = question_count * (MAX_RESPONSES_PER_FIXED_QUESTION + 2)
    if approved_model_responses > maximum:
        raise ValueError("approved model response limit is too broad")


@dataclass
class NativeToolOnlineCandidateCombinedV14(
    NativeToolOnlineCandidateCombinedV13
):
    real_authorization_validator: Callable[..., None] = field(
        init=False,
        default_factory=lambda: validate_combined_v14_real_authorization,
        repr=False,
    )
    terminal_repair_limit: int = field(init=False, default=2, repr=False)
    terminal_repair_instruction: str = field(
        init=False,
        default_factory=load_protocol_validation_feedback_prompt_v14,
        repr=False,
    )
    terminal_protocol_error_feedback_builder: Callable[
        [str, str, str], list[dict[str, Any]]
    ] = field(
        init=False,
        default_factory=lambda: terminal_protocol_issues_v14,
        repr=False,
    )


__all__ = [
    "COMBINED_PROMPT_VERSION",
    "NativeToolOnlineCandidateCombinedV14",
    "validate_combined_v14_real_authorization",
]
