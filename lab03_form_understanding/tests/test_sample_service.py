from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.model_client import VisionCallResult
from src.sample_service import run_custom_sample


class _CustomClient:
    def extract(self, image_path: Path) -> VisionCallResult:
        return VisionCallResult(
            response_text='{"fields":[],"warnings":[]}',
            requested_model="fixed-model",
            returned_model="fixed-model",
            finish_reason="stop",
            usage={},
            elapsed_seconds=0.01,
        )


class SampleServiceTests(unittest.TestCase):
    def test_custom_input_has_no_reference_or_automatic_correctness_claim(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            image_path = project_root / "data" / "local" / "uploads" / "custom.jpg"
            image_path.parent.mkdir(parents=True)
            image_path.write_bytes(b"fake")
            outcome = run_custom_sample(
                sample_id="custom-1",
                image_path=image_path,
                client=_CustomClient(),
                results_dir=project_root / "results",
                project_root=project_root,
            )
        self.assertIsNone(outcome["reference"])
        self.assertIsNone(outcome["comparison"])
        self.assertIn("不能自动判断内容是否正确", outcome["notice"])
        self.assertEqual(outcome["image_path"], "data/local/uploads/custom.jpg")


if __name__ == "__main__":
    unittest.main()
