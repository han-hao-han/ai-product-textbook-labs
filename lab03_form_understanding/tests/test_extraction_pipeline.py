from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.extraction_pipeline import run_extraction
from src.model_client import VisionCallResult
from src.response_parser import ModelResponseError


class _FakeVisionClient:
    def __init__(self, response_text: str | None = None, error: Exception | None = None):
        self.response_text = response_text
        self.error = error

    def extract(self, image_path: Path) -> VisionCallResult:
        if self.error is not None:
            raise self.error
        return VisionCallResult(
            response_text=str(self.response_text),
            requested_model="candidate-model",
            returned_model="candidate-model",
            finish_reason="stop",
            usage={"total_tokens": 10},
            elapsed_seconds=0.1,
        )


class ExtractionPipelineTests(unittest.TestCase):
    def test_saves_raw_and_parsed_history_without_updating_current(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            results_dir = Path(temp_dir) / "results"
            outcome = run_extraction(
                sample_id="sample-1",
                image_path=Path(temp_dir) / "sample.jpg",
                client=_FakeVisionClient('{"fields":[],"warnings":[]}'),
                results_dir=results_dir,
                update_current=False,
            )
            self.assertTrue(outcome["raw_path"].is_file())
            self.assertTrue(outcome["parsed_path"].is_file())
            self.assertFalse((results_dir / "current" / "sample-1.json").exists())
            self.assertEqual(outcome["response_text"], '{"fields":[],"warnings":[]}')

    def test_successful_formal_run_updates_current_after_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            results_dir = Path(temp_dir) / "results"
            outcome = run_extraction(
                sample_id="sample-1",
                image_path=Path(temp_dir) / "sample.jpg",
                client=_FakeVisionClient(
                    '{"fields":[{"key":"姓名","value":"张三"}],"warnings":[]}'
                ),
                results_dir=results_dir,
                update_current=True,
            )
            current_path = results_dir / "current" / "sample-1.json"
            self.assertEqual(outcome["current_path"], current_path)
            self.assertTrue(current_path.is_file())
            current = json.loads(current_path.read_text(encoding="utf-8"))
            self.assertEqual(current["result"]["fields"][0]["key"], "姓名")

    def test_schema_failure_keeps_existing_current_and_saves_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            results_dir = Path(temp_dir) / "results"
            current_path = results_dir / "current" / "sample-1.json"
            current_path.parent.mkdir(parents=True)
            current_path.write_text('{"previous":true}', encoding="utf-8")

            with self.assertRaises(ModelResponseError):
                run_extraction(
                    sample_id="sample-1",
                    image_path=Path(temp_dir) / "sample.jpg",
                    client=_FakeVisionClient('{"wrong":[]}'),
                    results_dir=results_dir,
                    update_current=True,
                )

            self.assertEqual(
                json.loads(current_path.read_text(encoding="utf-8")),
                {"previous": True},
            )
            self.assertEqual(len(list((results_dir / "failed").glob("*.json"))), 1)
            self.assertEqual(len(list((results_dir / "history" / "raw").glob("*.json"))), 1)

    def test_timeout_saves_redacted_failure_without_raw_response(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            results_dir = Path(temp_dir) / "results"
            with self.assertRaises(TimeoutError):
                run_extraction(
                    sample_id="sample-1",
                    image_path=Path(temp_dir) / "sample.jpg",
                    client=_FakeVisionClient(error=TimeoutError("secret-key timeout")),
                    results_dir=results_dir,
                    update_current=False,
                    secrets=("secret-key",),
                )
            failure_path = next((results_dir / "failed").glob("*.json"))
            failure_text = failure_path.read_text(encoding="utf-8")
            self.assertNotIn("secret-key", failure_text)
            self.assertIn("[REDACTED]", failure_text)
            self.assertFalse((results_dir / "history" / "raw").exists())


if __name__ == "__main__":
    unittest.main()
