from __future__ import annotations

import unittest

from src.field_comparator import compare_fields, mark_manual_review


class FieldComparatorTests(unittest.TestCase):
    def test_exact_match(self) -> None:
        comparison = compare_fields(
            [{"key": "姓名", "value": "张三"}],
            [{"key": "姓名", "value": "张三"}],
        )
        self.assertEqual(comparison["summary"]["exact_match"], 1)
        self.assertEqual(comparison["summary"]["reference_field_recognition_accuracy"], 1.0)

    def test_normalized_match(self) -> None:
        comparison = compare_fields(
            [{"key": "联系电话", "value": "ＡＢＣ  １２３"}],
            [{"key": "联系电话：", "value": "ABC 123"}],
        )
        self.assertEqual(comparison["summary"]["normalized_match"], 1)

    def test_wrong_value(self) -> None:
        comparison = compare_fields(
            [{"key": "金额", "value": "120元"}],
            [{"key": "金额", "value": "一百二十元"}],
        )
        self.assertEqual(comparison["summary"]["wrong_value"], 1)

    def test_detects_swapped_key_value_relations(self) -> None:
        comparison = compare_fields(
            [
                {"key": "姓名", "value": "张三"},
                {"key": "部门", "value": "研发部"},
            ],
            [
                {"key": "姓名", "value": "研发部"},
                {"key": "部门", "value": "张三"},
            ],
        )
        self.assertEqual(comparison["summary"]["key_value_mismatch"], 2)

    def test_reports_missing_and_extra_without_merging_duplicates(self) -> None:
        comparison = compare_fields(
            [
                {"key": "电话", "value": "111"},
                {"key": "电话", "value": "222"},
            ],
            [
                {"key": "电话", "value": "111"},
                {"key": "邮箱", "value": "a@example.com"},
            ],
        )
        self.assertEqual(comparison["summary"]["exact_match"], 1)
        self.assertEqual(comparison["summary"]["missing"], 1)
        self.assertEqual(comparison["summary"]["extra"], 1)

    def test_manual_review_requires_human_note(self) -> None:
        comparison = compare_fields(
            [{"key": "日期", "value": "2026年7月20日"}],
            [{"key": "日期", "value": "2026-07-20"}],
        )
        updated = mark_manual_review(comparison, 0, "日期格式不同，需人工确认")
        self.assertEqual(updated["summary"]["manual_review"], 1)
        self.assertEqual(comparison["summary"]["wrong_value"], 1)


if __name__ == "__main__":
    unittest.main()
