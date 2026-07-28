from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from src.model_client import ModelCallError, OpenAICompatibleVisionClient
from src.settings import ModelSettings


class _FakeCompletions:
    def __init__(self, response: object) -> None:
        self.response = response
        self.request = None

    def create(self, **request):
        self.request = request
        return self.response


class _FakeClient:
    def __init__(self, response: object) -> None:
        self.completions = _FakeCompletions(response)
        self.chat = SimpleNamespace(completions=self.completions)


class ModelClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = ModelSettings(
            api_key="test-secret",
            base_url="https://example.com/v1",
            model="qwen3.7-plus-2026-05-26",
            temperature=0,
            timeout_seconds=30,
        )

    def test_returns_only_safe_call_metadata(self) -> None:
        usage = SimpleNamespace(model_dump=lambda mode: {"total_tokens": 12})
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content='{"fields":[],"warnings":[]}'
                    ),
                    finish_reason="stop",
                )
            ],
            model="qwen3.7-plus-2026-05-26",
            usage=usage,
        )
        fake_client = _FakeClient(response)
        client = OpenAICompatibleVisionClient(self.settings, client=fake_client)
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "sample.jpg"
            image_path.write_bytes(b"fake")
            result = client.extract(image_path, prompt="输出JSON")

        self.assertEqual(result.usage, {"total_tokens": 12})
        self.assertEqual(
            fake_client.completions.request["response_format"],
            {"type": "json_object"},
        )
        self.assertNotIn("api_key", fake_client.completions.request)

    def test_rejects_empty_assistant_content(self) -> None:
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=None), finish_reason="stop"
                )
            ],
            model=self.settings.model,
            usage=None,
        )
        client = OpenAICompatibleVisionClient(
            self.settings, client=_FakeClient(response)
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "sample.jpg"
            image_path.write_bytes(b"fake")
            with self.assertRaises(ModelCallError):
                client.extract(image_path, prompt="输出JSON")


if __name__ == "__main__":
    unittest.main()
