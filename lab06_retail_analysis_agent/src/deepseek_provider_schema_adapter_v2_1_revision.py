"""DeepSeek-only transport adapter for the frozen seven tool schemas.

The internal Pydantic models remain the business authority.  This module
only translates schema constructs that DeepSeek strict-tools Beta does not
document reliably, and reverses one explicit transport sentinel before
program-side validation.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from src.deepseek_client import DeepSeekClientError


DEEPSEEK_NONE_SENTINEL = "__NONE__"
DEEPSEEK_UNSUPPORTED_STRICT_KEYWORDS = {
    "minLength",
    "maxLength",
    "minItems",
    "maxItems",
}
NULLABLE_ARGUMENT_FIELDS = {
    "get_sales_overview": frozenset({"start_date", "end_date"}),
    "rank_products": frozenset({"start_date", "end_date"}),
    "analyze_regions": frozenset(
        {"start_date", "end_date", "excluded_country"}
    ),
    "analyze_time_trend": frozenset({"start_date", "end_date"}),
    "analyze_customers": frozenset({"start_date", "end_date"}),
    "compare_segments": frozenset({"start_date", "end_date"}),
}


class DeepSeekProviderSchemaAdapterError(DeepSeekClientError):
    """Raised when provider arguments violate the transport boundary."""


def adapt_deepseek_provider_schema(
    provider_schema: dict[str, Any],
) -> dict[str, Any]:
    """Return a DeepSeek-compatible copy without changing internal schemas."""

    adapted = deepcopy(provider_schema)

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            for keyword in DEEPSEEK_UNSUPPORTED_STRICT_KEYWORDS:
                node.pop(keyword, None)

            constant = node.get("const")
            if isinstance(constant, (str, bool)):
                node.pop("const")
                node["enum"] = [constant]

            alternatives = node.get("anyOf")
            if isinstance(alternatives, list):
                replaced_null = False
                replacement: list[Any] = []
                for alternative in alternatives:
                    if (
                        isinstance(alternative, dict)
                        and alternative.get("type") == "null"
                        and len(alternative) == 1
                    ):
                        replacement.append(
                            {
                                "type": "string",
                                "enum": [DEEPSEEK_NONE_SENTINEL],
                                "description": (
                                    "DeepSeek传输层空值；必须原样输出"
                                    f"{DEEPSEEK_NONE_SENTINEL}。"
                                ),
                            }
                        )
                        replaced_null = True
                    else:
                        replacement.append(alternative)
                if replaced_null:
                    node["anyOf"] = replacement
                    original = str(node.get("description") or "").strip()
                    transport_note = (
                        "DeepSeek工具调用不得输出JSON null或字符串null；"
                        f"无值时必须输出{DEEPSEEK_NONE_SENTINEL}。"
                    )
                    node["description"] = (
                        f"{original} {transport_note}".strip()
                    )

            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(adapted)
    return adapted


def normalize_deepseek_provider_arguments(
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Translate only the frozen sentinel; never repair other model values."""

    normalized = deepcopy(arguments)
    nullable_fields = NULLABLE_ARGUMENT_FIELDS.get(tool_name, frozenset())
    for field_name, value in normalized.items():
        if value != DEEPSEEK_NONE_SENTINEL:
            continue
        if field_name not in nullable_fields:
            raise DeepSeekProviderSchemaAdapterError(
                f"{tool_name}.{field_name}不允许DeepSeek空值哨兵"
            )
        normalized[field_name] = None
    return normalized
