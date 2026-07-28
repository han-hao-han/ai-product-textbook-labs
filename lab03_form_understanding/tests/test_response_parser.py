from __future__ import annotations

import unittest

from src.response_parser import ModelResponseError, parse_model_response


class ModelResponseParserTests(unittest.TestCase):
    def test_parses_valid_json(self) -> None:
        result = parse_model_response(
            '{"fields":[{"key":"姓名","value":"张三"}],"warnings":[]}'
        )
        self.assertEqual(len(result.fields), 1)

    def test_rejects_markdown_code_fence(self) -> None:
        with self.assertRaises(ModelResponseError) as context:
            parse_model_response('```json\n{"fields":[],"warnings":[]}\n```')
        self.assertEqual(context.exception.stage, "json_parse")

    def test_rejects_non_json(self) -> None:
        with self.assertRaises(ModelResponseError) as context:
            parse_model_response("识别结果为空")
        self.assertEqual(context.exception.stage, "json_parse")

    def test_rejects_empty_response(self) -> None:
        with self.assertRaises(ModelResponseError) as context:
            parse_model_response("  ")
        self.assertEqual(context.exception.stage, "empty_response")

    def test_reports_schema_failure_separately(self) -> None:
        with self.assertRaises(ModelResponseError) as context:
            parse_model_response('{"items":[],"warnings":[]}')
        self.assertEqual(context.exception.stage, "schema_validation")


if __name__ == "__main__":
    unittest.main()
