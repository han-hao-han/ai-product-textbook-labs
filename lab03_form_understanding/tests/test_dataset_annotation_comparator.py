from __future__ import annotations

import unittest

from src.dataset_annotation_comparator import compare_dataset_annotation


class DatasetAnnotationComparatorTests(unittest.TestCase):
    def test_exact_and_normalized_matches_are_consistent(self) -> None:
        comparison = compare_dataset_annotation(
            [
                {"key": "姓名", "value": "张三"},
                {"key": "电话", "value": "ＡＢＣ　123"},
            ],
            [
                {"key": "姓名", "value": "张三"},
                {"key": "电话：", "value": "ABC 123"},
            ],
        )

        self.assertEqual(comparison["summary"]["exact_match"], 1)
        self.assertEqual(comparison["summary"]["normalized_match"], 1)
        self.assertEqual(
            comparison["summary"]["dataset_annotation_consistency_rate"], 1.0
        )
        self.assertFalse(comparison["interpretation"]["is_accuracy_metric"])

    def test_containment_is_only_a_diagnostic_hint(self) -> None:
        comparison = compare_dataset_annotation(
            [{"key": "意见", "value": "合格"}],
            [{"key": "意见", "value": "合格\n2026年7月23日"}],
        )

        row = comparison["dataset_annotation_results"][0]
        self.assertEqual(row["status"], "different_value")
        self.assertIn(
            "reference_value_contained_in_model_value", row["diagnostic_hints"]
        )
        self.assertEqual(
            comparison["summary"]["dataset_annotation_consistency_rate"], 0.0
        )

    def test_same_value_different_key_is_only_a_diagnostic_hint(self) -> None:
        comparison = compare_dataset_annotation(
            [{"key": "出生", "value": "1993年1月29日"}],
            [{"key": "出生年月", "value": "1993年1月29日"}],
        )

        self.assertEqual(
            comparison["dataset_annotation_results"][0]["status"],
            "not_in_model_output",
        )
        model_only = comparison["model_only_fields"][0]
        self.assertEqual(model_only["status"], "not_in_dataset_annotation")
        self.assertIn("same_value_different_key", model_only["diagnostic_hints"])

    def test_checkbox_difference_is_not_automatically_equivalent(self) -> None:
        comparison = compare_dataset_annotation(
            [{"key": "是否通过", "value": "☑是 □否"}],
            [{"key": "是否通过", "value": "□是 ☑否"}],
        )

        row = comparison["dataset_annotation_results"][0]
        self.assertEqual(row["status"], "different_value")
        self.assertIn("checkbox_symbol_difference", row["diagnostic_hints"])
        self.assertEqual(
            comparison["summary"]["dataset_annotation_consistency_rate"], 0.0
        )

    def test_swapped_relations_are_reported_without_correctness_wording(self) -> None:
        comparison = compare_dataset_annotation(
            [
                {"key": "姓名", "value": "张三"},
                {"key": "部门", "value": "研发部"},
            ],
            [
                {"key": "姓名", "value": "研发部"},
                {"key": "部门", "value": "张三"},
            ],
        )

        self.assertEqual(comparison["summary"]["different_pairing"], 2)
        self.assertNotIn(
            "reference_field_recognition_accuracy", comparison["summary"]
        )

    def test_same_key_multiline_values_can_be_diagnosed_as_model_merge(self) -> None:
        comparison = compare_dataset_annotation(
            [
                {"key": "工作经历", "value": "第一行"},
                {"key": "工作经历", "value": "第二行"},
            ],
            [{"key": "工作经历", "value": "第一行 第二行"}],
        )

        merge_links = [
            link
            for link in comparison["diagnostic_links"]
            if "same_key_multiple_dataset_values_combined"
            in link["diagnostic_hints"]
        ]
        self.assertEqual(len(merge_links), 1)
        self.assertEqual(merge_links[0]["dataset_annotation_indices"], [0, 1])
        self.assertEqual(
            comparison["summary"]["dataset_annotation_consistency_rate"], 0.0
        )

    def test_high_similarity_is_a_scored_hint_not_a_match(self) -> None:
        comparison = compare_dataset_annotation(
            [{"key": "技术负责人意见", "value": "符合要求"}],
            [{"key": "技术负责人意见栏", "value": "基本符合要求"}],
        )

        links = comparison["diagnostic_links"]
        self.assertTrue(
            any("high_key_similarity" in link["diagnostic_hints"] for link in links)
        )
        self.assertTrue(
            any(
                "high_value_similarity" in link["diagnostic_hints"]
                for link in links
            )
        )
        self.assertEqual(
            comparison["summary"]["dataset_annotation_consistency_rate"], 0.0
        )


if __name__ == "__main__":
    unittest.main()
