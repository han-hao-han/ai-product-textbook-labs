"""Convert safe terminal Schema failures into bounded model feedback."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from src.report_terminal_protocol_guard_v2_3_4_2 import (
    MODEL_CONTROL_ADAPTER_V2_3_4_2,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_VALIDATION_FEEDBACK_PROMPT_PATH = (
    PROJECT_ROOT / "prompts" / "native_tool_protocol_validation_feedback_v14.md"
)
PROTOCOL_VALIDATION_FEEDBACK_VERSION = (
    "1.5.6-h3-protocol-validation-feedback-v14"
)


def terminal_protocol_issues_v14(
    code: str, message: str, content: str,
) -> list[dict[str, Any]]:
    if code != "model_terminal_schema_invalid":
        return []
    try:
        MODEL_CONTROL_ADAPTER_V2_3_4_2.validate_json(content)
    except ValidationError as exc:
        issues: list[dict[str, Any]] = []
        for error in exc.errors(include_url=False, include_input=False):
            location = list(error["loc"])
            if not location or location[0] != "ModelFinalReportResponseV2_3_4_2":
                continue
            issues.append(
                {
                    "code": "model_terminal_schema_invalid",
                    "location": ".".join(str(item) for item in location[1:]),
                    "validation_type": error["type"],
                    "message": error["msg"],
                }
            )
        return issues or [
            {
                "code": code,
                "location": "terminal_response",
                "message": message,
            }
        ]
    except json.JSONDecodeError:
        return [
            {
                "code": code,
                "location": "terminal_response",
                "message": "return one complete JSON object",
            }
        ]
    return []


def load_protocol_validation_feedback_prompt_v14() -> str:
    return PROTOCOL_VALIDATION_FEEDBACK_PROMPT_PATH.read_text(
        encoding="utf-8"
    ).strip()


__all__ = [
    "PROTOCOL_VALIDATION_FEEDBACK_PROMPT_PATH",
    "PROTOCOL_VALIDATION_FEEDBACK_VERSION",
    "load_protocol_validation_feedback_prompt_v14",
    "terminal_protocol_issues_v14",
]
