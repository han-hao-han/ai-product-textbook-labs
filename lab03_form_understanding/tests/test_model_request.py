from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.model_request import build_chat_completion_request, image_to_data_url


class ModelRequestTests(unittest.TestCase):
    def test_builds_openai_compatible_vision_request(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "sample.jpg"
            image_path.write_bytes(b"fake-jpeg-for-request-construction")
            request = build_chat_completion_request(
                image_path,
                model="qwen3.7-plus-2026-05-26",
                prompt="请以JSON格式返回fields和warnings。",
            )

        self.assertEqual(request["response_format"], {"type": "json_object"})
        self.assertEqual(request["extra_body"], {"enable_thinking": False})
        self.assertEqual(request["temperature"], 0)
        data_url = request["messages"][1]["content"][0]["image_url"]["url"]
        self.assertTrue(data_url.startswith("data:image/jpeg;base64,"))
        self.assertNotIn("api_key", request)

    def test_rejects_unsupported_image_type(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "sample.txt"
            image_path.write_text("not an image", encoding="utf-8")
            with self.assertRaises(ValueError):
                image_to_data_url(image_path)


if __name__ == "__main__":
    unittest.main()
