from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.model_client import VisionCallResult
from src.validation_runner import run_fixed_validation


class _SequencedClient:
    def __init__(self, failed_sample_id: str | None = None) -> None:
        self.failed_sample_id = failed_sample_id
        self.calls: list[str] = []

    def extract(self, image_path: Path) -> VisionCallResult:
        sample_id = image_path.stem
        self.calls.append(sample_id)
        if sample_id == self.failed_sample_id:
            raise TimeoutError("secret-key simulated timeout")
        return VisionCallResult(
            response_text='{"fields":[{"key":"字段","value":"值"}],"warnings":[]}',
            requested_model="fixed-model",
            returned_model="fixed-model",
            finish_reason="stop",
            usage={"total_tokens": 10},
            elapsed_seconds=0.01,
        )


class ValidationRunnerTests(unittest.TestCase):
    def test_failure_continues_in_fixed_serial_order_and_marks_incomplete(self) -> None:
        validation_samples = _validation_samples()
        documents = [_document(item["sample_id"]) for item in validation_samples]
        client = _SequencedClient(failed_sample_id="sample-3")
        progress_events: list[tuple[int, int, str, str]] = []
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            images_dir = project_root / "images"
            images_dir.mkdir()
            for item in validation_samples:
                (images_dir / f"{item['sample_id']}.jpg").write_bytes(b"fake")

            outcome = run_fixed_validation(
                validation_samples=validation_samples,
                documents=documents,
                images_dir=images_dir,
                client=client,
                results_dir=project_root / "results",
                project_root=project_root,
                secrets=("secret-key",),
                progress_callback=lambda *event: progress_events.append(event),
            )

            payload = outcome["payload"]
            self.assertTrue(outcome["output_path"].is_file())
            self.assertFalse(payload["complete"])
            self.assertEqual(payload["successful_sample_count"], 5)
            self.assertEqual(payload["failed_sample_count"], 1)
            self.assertEqual(client.calls, [f"sample-{index}" for index in range(1, 7)])
            self.assertEqual(len(progress_events), 12)
            self.assertEqual(payload["samples"][2]["status"], "failed")
            self.assertNotIn("secret-key", payload["samples"][2]["message"])
            self.assertEqual(
                payload["engineering_summary"]["total_field_count"],
                5,
            )
            self.assertEqual(
                payload["overall_dataset_annotation_diagnostic"][
                    "dataset_annotation_field_count"
                ],
                5,
            )
            self.assertEqual(
                payload["engineering_summary"]["total_warning_count"], 0
            )
            self.assertEqual(
                payload["difficulty_summary"]["medium"]["failed_sample_count"], 1
            )
            self.assertFalse(
                (project_root / "results" / "current" / "sample-3.json").exists()
            )
            self.assertTrue(
                (project_root / "results" / "current" / "sample-6.json").is_file()
            )

    def test_rejects_partial_formal_validation_set(self) -> None:
        with self.assertRaisesRegex(ValueError, "6张"):
            run_fixed_validation(
                validation_samples=_validation_samples()[:1],
                documents=[],
                images_dir=Path("images"),
                client=_SequencedClient(),
                results_dir=Path("results"),
                project_root=Path("."),
            )

    def test_six_successes_mark_validation_complete(self) -> None:
        validation_samples = _validation_samples()
        documents = [_document(item["sample_id"]) for item in validation_samples]
        client = _SequencedClient()
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            images_dir = project_root / "images"
            images_dir.mkdir()
            for item in validation_samples:
                (images_dir / f"{item['sample_id']}.jpg").write_bytes(b"fake")
            outcome = run_fixed_validation(
                validation_samples=validation_samples,
                documents=documents,
                images_dir=images_dir,
                client=client,
                results_dir=project_root / "results",
                project_root=project_root,
            )
        payload = outcome["payload"]
        self.assertTrue(payload["complete"])
        self.assertEqual(payload["successful_sample_count"], 6)
        self.assertEqual(payload["failed_sample_count"], 0)
        self.assertEqual(
            payload["engineering_summary"]["total_field_count"],
            6,
        )
        self.assertEqual(
            payload["engineering_summary"]["total_warning_count"], 0
        )
        self.assertFalse(payload["metadata"]["field_accuracy_included"])
        self.assertNotIn("overall_final_reference_summary", payload)

    def test_unreviewed_references_do_not_block_engineering_validation(self) -> None:
        validation_samples = _validation_samples()
        documents = [_document(item["sample_id"]) for item in validation_samples]
        client = _SequencedClient()
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            images_dir = project_root / "images"
            images_dir.mkdir()
            for item in validation_samples:
                (images_dir / f"{item['sample_id']}.jpg").write_bytes(b"fake")
            outcome = run_fixed_validation(
                validation_samples=validation_samples,
                documents=documents,
                images_dir=images_dir,
                client=client,
                results_dir=project_root / "results",
                project_root=project_root,
            )
        self.assertTrue(outcome["payload"]["complete"])
        self.assertEqual(
            client.calls, [f"sample-{index}" for index in range(1, 7)]
        )


def _validation_samples() -> list[dict]:
    groups = ["simple", "simple", "medium", "medium", "complex", "complex"]
    return [
        {
            "sample_id": f"sample-{index}",
            "validation_order": index,
            "difficulty_group": groups[index - 1],
        }
        for index in range(1, 7)
    ]


def _document(sample_id: str) -> dict:
    return {
        "id": sample_id,
        "img": {"fname": f"{sample_id}.jpg"},
        "document": [
            {
                "id": 1,
                "text": "字段",
                "label": "question",
                "linking": [[1, 2]],
                "words": [],
            },
            {
                "id": 2,
                "text": "值",
                "label": "answer",
                "linking": [[1, 2]],
                "words": [],
            },
        ],
    }


if __name__ == "__main__":
    unittest.main()
