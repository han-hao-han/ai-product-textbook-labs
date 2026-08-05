"""Strict JSON decision protocol for recipe-based V2.1 planning."""

from __future__ import annotations

import json
from typing import Any, TypeAlias

from pydantic import ValidationError

from src.agent_decision_v2 import (
    BoundaryDecisionV2,
    ClarificationDecisionV2,
)
from src.analysis_recipes_v2_1 import AnalysisRecipeDecisionV2_1


DecisionV2_1: TypeAlias = (
    ClarificationDecisionV2
    | BoundaryDecisionV2
    | AnalysisRecipeDecisionV2_1
)


class DecisionProtocolV2_1Error(ValueError):
    """Raised when the V2.1 JSON decision violates its schema."""


def parse_decision_v2_1(content: str) -> DecisionV2_1:
    try:
        payload: Any = json.loads(content)
    except json.JSONDecodeError as exc:
        raise DecisionProtocolV2_1Error(
            "V2.1决策必须是合法JSON"
        ) from exc
    if not isinstance(payload, dict):
        raise DecisionProtocolV2_1Error(
            "V2.1决策顶层必须是JSON对象"
        )
    decision_type = payload.get("decision_type")
    model = {
        "clarification": ClarificationDecisionV2,
        "boundary": BoundaryDecisionV2,
        "analysis_recipe": AnalysisRecipeDecisionV2_1,
    }.get(decision_type)
    if model is None:
        raise DecisionProtocolV2_1Error(
            "decision_type不属于V2.1白名单"
        )
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise DecisionProtocolV2_1Error(
            f"V2.1决策Schema校验失败：{exc}"
        ) from exc
