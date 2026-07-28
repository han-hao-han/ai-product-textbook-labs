from __future__ import annotations

import unittest

from pydantic import ValidationError

from src.schemas import FormExtractionResult


class FormExtractionSchemaTests(unittest.TestCase):
    def test_accepts_minimum_valid_result(self) -> None:
        result = FormExtractionResult.model_validate(
            {"fields": [{"key": "姓名", "value": "张三"}], "warnings": []}
        )
        self.assertEqual(result.fields[0].key, "姓名")

    def test_rejects_extra_model_owned_fields(self) -> None:
        with self.assertRaises(ValidationError):
            FormExtractionResult.model_validate(
                {
                    "fields": [{"key": "姓名", "value": "张三", "confidence": 0.9}],
                    "warnings": [],
                    "sample_id": "zh_train_103",
                }
            )

    def test_rejects_non_string_values(self) -> None:
        with self.assertRaises(ValidationError):
            FormExtractionResult.model_validate(
                {"fields": [{"key": "金额", "value": 120}], "warnings": []}
            )


if __name__ == "__main__":
    unittest.main()
