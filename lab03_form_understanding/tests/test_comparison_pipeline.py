from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from src.comparison_pipeline import (
    ComparisonInputError,
    compare_saved_result,
    load_saved_model_result,
)


class ComparisonPipelineTests(unittest.TestCase):
    def test_compares_dataset_annotation_and_withholds_unreviewed_accuracy(
        self,
    ) -> None:
        document = _document()
        original_document = copy.deepcopy(document)
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            result_path = project_root / "results" / "current" / "sample-1.json"
            result_path.parent.mkdir(parents=True)
            result_path.write_text(
                json.dumps(_saved_result(), ensure_ascii=False), encoding="utf-8"
            )
            original_result_text = result_path.read_text(encoding="utf-8")

            outcome = compare_saved_result(
                sample_id="sample-1",
                result_path=result_path,
                document=document,
                comparisons_dir=project_root / "results" / "comparisons",
                project_root=project_root,
            )

            self.assertTrue(outcome["output_path"].is_file())
            payload = outcome["payload"]
            self.assertEqual(
                payload["dataset_annotation_comparison"]["summary"][
                    "dataset_annotation_consistency_rate"
                ],
                1.0,
            )
            self.assertFalse(
                payload["final_reference"]["available_for_accuracy"]
            )
            self.assertIsNone(payload["final_reference_comparison"])
            self.assertEqual(
                payload["metadata"]["source_result_file"],
                "results/current/sample-1.json",
            )
            row = payload["dataset_annotation_comparison"][
                "dataset_annotation_results"
            ][0]
            self.assertEqual(row["question_entity_id"], 1)
            self.assertEqual(row["answer_entity_id"], 2)
            self.assertEqual(document, original_document)
            self.assertEqual(result_path.read_text(encoding="utf-8"), original_result_text)

    def test_reviewed_reference_enables_accuracy_metric(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            result_path = project_root / "results" / "current" / "sample-1.json"
            result_path.parent.mkdir(parents=True)
            result_path.write_text(
                json.dumps(_saved_result(), ensure_ascii=False), encoding="utf-8"
            )
            review_dir = project_root / "data" / "local" / "sample_reviews"
            review_dir.mkdir(parents=True)
            (review_dir / "sample-1.json").write_text(
                json.dumps(_confirmed_review(), ensure_ascii=False),
                encoding="utf-8",
            )

            outcome = compare_saved_result(
                sample_id="sample-1",
                result_path=result_path,
                document=_document(),
                comparisons_dir=project_root / "results" / "comparisons",
                project_root=project_root,
                review_records_dir=review_dir,
            )

            payload = outcome["payload"]
            self.assertTrue(
                payload["final_reference"]["available_for_accuracy"]
            )
            self.assertEqual(
                payload["final_reference_comparison"]["summary"][
                    "reference_field_recognition_accuracy"
                ],
                1.0,
            )
            self.assertEqual(payload["metadata"]["comparison_version"], "v2")

    def test_rejects_result_from_another_sample(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result_path = Path(temp_dir) / "result.json"
            payload = _saved_result()
            payload["metadata"]["sample_id"] = "other-sample"
            result_path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ComparisonInputError, "不一致"):
                load_saved_model_result(result_path, expected_sample_id="sample-1")

    def test_rejects_saved_result_that_no_longer_matches_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result_path = Path(temp_dir) / "result.json"
            payload = _saved_result()
            payload["result"]["confidence"] = 0.9
            result_path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ComparisonInputError, "Schema v1"):
                load_saved_model_result(result_path, expected_sample_id="sample-1")

    def test_missing_result_explicitly_points_to_step02(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "missing.json"
            with self.assertRaisesRegex(FileNotFoundError, "step02_extract_form.py"):
                load_saved_model_result(missing, expected_sample_id="sample-1")


def _saved_result() -> dict:
    return {
        "metadata": {
            "sample_id": "sample-1",
            "run_id": "run-001",
            "model": "fixed-model",
            "prompt_version": "v1",
            "schema_version": "v1",
        },
        "result": {
            "fields": [{"key": "姓名", "value": "张三"}],
            "warnings": [],
        },
    }


def _document() -> dict:
    return {
        "id": "sample-1",
        "img": {"fname": "sample.jpg"},
        "document": [
            {
                "id": 1,
                "text": "姓名",
                "label": "question",
                "linking": [[1, 2]],
                "words": [],
            },
            {
                "id": 2,
                "text": "张三",
                "label": "answer",
                "linking": [[1, 2]],
                "words": [],
            },
        ],
    }


def _confirmed_review() -> dict:
    return {
        "schema_version": "sample-review-v1",
        "sample_id": "sample-1",
        "dataset": "XFUND v1.0 zh",
        "privacy_review": {
            "status": "passed",
            "national_id": "not_present",
        },
        "annotation_review": {
            "status": "confirmed",
            "corrections": [],
        },
        "final_reference_status": "source_annotation_confirmed",
    }


if __name__ == "__main__":
    unittest.main()
