from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from src.deepseek_client import ChatCompletionResult, ProviderToolCall
from src.deepseek_provider_schema_adapter_v2_1_revision import (
    DEEPSEEK_NONE_SENTINEL,
    DeepSeekProviderSchemaAdapterError,
    adapt_deepseek_provider_schema,
    normalize_deepseek_provider_arguments,
)
from src.fixed_question_validation import load_frozen_questions
from src.mock_h2_registry import FrozenH2MockRegistry
from src.mock_native_tool_client_v2_1_revision import (
    FrozenQuestionNativeToolMockClient,
)
from src.native_tool_agent_v2_1_revision import (
    RetailNativeToolAgentV2_1Revision,
)


ROOT = Path(__file__).resolve().parents[1]


def _walk(value: Any):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


class SentinelQ04Client:
    def __init__(self) -> None:
        self.delegate = FrozenQuestionNativeToolMockClient()

    def complete_strict_tools(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: str = "auto",
    ) -> ChatCompletionResult:
        result = self.delegate.complete_strict_tools(
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
        )
        if result.tool_calls:
            selected = result.tool_calls[0]
            if selected.tool_name == "analyze_time_trend":
                provider_arguments = dict(selected.arguments)
                provider_arguments["start_date"] = DEEPSEEK_NONE_SENTINEL
                provider_arguments["end_date"] = DEEPSEEK_NONE_SENTINEL
                return ChatCompletionResult(
                    finish_reason=result.finish_reason,
                    content=result.content,
                    tool_calls=(
                        ProviderToolCall(
                            provider_call_id=selected.provider_call_id,
                            tool_name=selected.tool_name,
                            arguments=provider_arguments,
                        ),
                    ),
                    raw_response={
                        **result.raw_response,
                        "provider_sentinel": True,
                    },
                    usage=result.usage,
                )
        return result


class DeepSeekProviderSchemaAdapterV2_1RevisionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.schemas = [
            adapt_deepseek_provider_schema(item)
            for item in FrozenH2MockRegistry().provider_schemas()
        ]

    def test_contract_is_frozen_without_reopening_business_boundaries(self) -> None:
        contract = json.loads(
            (
                ROOT
                / "config"
                / "h3_deepseek_provider_schema_adapter_v2_1_revision.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(contract["status"], "frozen_by_user")
        self.assertTrue(
            contract["scope"]["internal_pydantic_schemas_unchanged"]
        )
        self.assertTrue(contract["scope"]["seven_tool_whitelist_unchanged"])
        self.assertTrue(
            contract["scope"]["model_still_selects_tool_and_business_arguments"]
        )

    def test_all_seven_provider_schemas_remove_null_and_nonnumeric_const(self) -> None:
        self.assertEqual(len(self.schemas), 7)
        for schema in self.schemas:
            for node in _walk(schema):
                if not isinstance(node, dict):
                    continue
                self.assertNotEqual(node.get("type"), "null")
                if "const" in node:
                    self.assertIsInstance(node["const"], (int, float))
                    self.assertNotIsInstance(node["const"], bool)
                for keyword in (
                    "minLength",
                    "maxLength",
                    "minItems",
                    "maxItems",
                ):
                    self.assertNotIn(keyword, node)

    def test_q06_provider_schema_uses_exact_enum_and_none_sentinel(self) -> None:
        trend = next(
            item for item in self.schemas
            if item["function"]["name"] == "analyze_time_trend"
        )
        properties = trend["function"]["parameters"]["properties"]
        self.assertEqual(properties["grain"]["enum"], ["month"])
        self.assertNotIn("const", properties["grain"])
        for field_name in ("start_date", "end_date"):
            alternatives = properties[field_name]["anyOf"]
            self.assertIn(
                {"type": "string", "enum": [DEEPSEEK_NONE_SENTINEL],
                 "description": "DeepSeek传输层空值；必须原样输出__NONE__。"},
                alternatives,
            )

    def test_only_exact_sentinel_is_normalized(self) -> None:
        original = {
            "period": "complete_months_only",
            "start_date": DEEPSEEK_NONE_SENTINEL,
            "end_date": DEEPSEEK_NONE_SENTINEL,
            "grain": "month",
            "metric": "sales_amount",
            "exclude_incomplete_periods": True,
        }
        normalized = normalize_deepseek_provider_arguments(
            "analyze_time_trend", original
        )
        self.assertIsNone(normalized["start_date"])
        self.assertIsNone(normalized["end_date"])
        self.assertEqual(normalized["grain"], "month")
        self.assertEqual(original["start_date"], DEEPSEEK_NONE_SENTINEL)

        invalid = normalize_deepseek_provider_arguments(
            "analyze_time_trend",
            {**original, "start_date": "null", "grain": "monthly"},
        )
        self.assertEqual(invalid["start_date"], "null")
        self.assertEqual(invalid["grain"], "monthly")

    def test_sentinel_is_rejected_on_nonnullable_field(self) -> None:
        with self.assertRaises(DeepSeekProviderSchemaAdapterError):
            normalize_deepseek_provider_arguments(
                "analyze_time_trend",
                {"grain": DEEPSEEK_NONE_SENTINEL},
            )

    def test_agent_traces_provider_and_normalized_arguments_separately(self) -> None:
        agent = RetailNativeToolAgentV2_1Revision(
            client=SentinelQ04Client(),
            registry=FrozenH2MockRegistry(),
        )
        outcome = agent.run_turn(
            session_id="SESSION-provider-sentinel",
            turn_id="TURN-004",
            question=load_frozen_questions()["Q04"]["question"],
        )

        self.assertEqual(outcome.status, "completed")
        first_trace = agent.last_trace[0]
        self.assertEqual(
            first_trace.selected_arguments["start_date"],
            DEEPSEEK_NONE_SENTINEL,
        )
        self.assertIsNone(first_trace.normalized_arguments["start_date"])
        self.assertIsNone(outcome.tool_calls[0].arguments["start_date"])


if __name__ == "__main__":
    unittest.main()
