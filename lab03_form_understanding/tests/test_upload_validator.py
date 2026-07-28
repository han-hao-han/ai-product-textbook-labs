from __future__ import annotations

import tempfile
import unittest
from io import BytesIO
from pathlib import Path

from PIL import Image

from src.upload_validator import (
    MAX_UPLOAD_BYTES,
    UploadValidationError,
    save_validated_upload,
    validate_uploaded_image,
)


class UploadValidatorTests(unittest.TestCase):
    def test_accepts_a_real_png_and_saves_with_generated_name(self) -> None:
        data = _png_bytes()
        self.assertEqual(validate_uploaded_image(data), ".png")
        with tempfile.TemporaryDirectory() as temp_dir:
            sample_id, output_path = save_validated_upload(data, Path(temp_dir))
            self.assertTrue(sample_id.startswith("custom_"))
            self.assertEqual(output_path.name, f"{sample_id}.png")
            self.assertTrue(output_path.is_file())

    def test_rejects_non_image_bytes(self) -> None:
        with self.assertRaises(UploadValidationError):
            validate_uploaded_image(b"not-an-image")

    def test_rejects_oversized_input_before_decoding(self) -> None:
        with self.assertRaisesRegex(UploadValidationError, "10MB"):
            validate_uploaded_image(b"x" * (MAX_UPLOAD_BYTES + 1))


def _png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (2, 2), color="white").save(buffer, format="PNG")
    return buffer.getvalue()


if __name__ == "__main__":
    unittest.main()
