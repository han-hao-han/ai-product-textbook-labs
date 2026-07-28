from __future__ import annotations

import copy
import unittest
from pathlib import Path

from src.subset_config import (
    SubsetConfigError,
    load_teaching_subset,
    main_observation_ids,
    validate_teaching_subset,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class SubsetConfigTests(unittest.TestCase):
    def test_current_main_and_observation_samples_are_unique(self) -> None:
        config = load_teaching_subset(PROJECT_ROOT / "configs" / "teaching_subset.json")

        self.assertEqual(
            main_observation_ids(config),
            {"zh_train_136", "zh_train_115", "zh_train_16", "zh_train_29"},
        )
        self.assertEqual(config["validation"]["status"], "frozen_user_confirmed")
        self.assertEqual(
            [item["sample_id"] for item in config["validation"]["samples"]],
            [
                "zh_train_30",
                "zh_train_85",
                "zh_train_58",
                "zh_train_65",
                "zh_train_132",
                "zh_train_141",
            ],
        )
        self.assertEqual(
            config["annotation_review"],
            "main_completed_fixed_validation_diagnostic_only",
        )
        self.assertEqual(
            config["validation"]["evaluation_scope"],
            "visual_model_call_and_engineering_flow",
        )
        self.assertFalse(config["validation"]["field_accuracy_required"])
        self.assertEqual(
            config["validation"]["dataset_annotation_usage"],
            "optional_diagnostic_only",
        )
        self.assertEqual(
            config["h4_confirmation"]["status"],
            "passed_user_confirmed",
        )
        self.assertEqual(
            config["h4_confirmation"]["validation_run_id"],
            "20260723T100048_257627Z",
        )
        self.assertEqual(
            config["h4_confirmation"]["successful_sample_count"], 6
        )
        self.assertEqual(
            config["h4_confirmation"]["failed_sample_count"], 0
        )

    def test_rejects_overlap_between_fixed_sets(self) -> None:
        config = load_teaching_subset(PROJECT_ROOT / "configs" / "teaching_subset.json")
        invalid = copy.deepcopy(config)
        invalid["validation"]["samples"] = [
            {"sample_id": config["main"]["sample_id"]}
        ]

        with self.assertRaisesRegex(SubsetConfigError, "重叠"):
            validate_teaching_subset(invalid)


if __name__ == "__main__":
    unittest.main()
