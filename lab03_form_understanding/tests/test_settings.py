from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.settings import (
    load_model_candidate,
    load_model_settings,
    require_h3_frozen,
)


class ModelSettingsTests(unittest.TestCase):
    def test_loads_candidate_defaults_without_exposing_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text("LLM_API_KEY=test-secret\n", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True):
                settings = load_model_settings(env_path)
        self.assertEqual(settings.model, "qwen3.7-plus-2026-05-26")
        self.assertEqual(
            settings.base_url,
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        )

    def test_rejects_missing_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / "missing.env"
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaisesRegex(ValueError, "LLM_API_KEY"):
                    load_model_settings(env_path)

    def test_rejects_a_different_model_during_h3_verification(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text(
                "LLM_API_KEY=test-secret\nLLM_MODEL=another-model\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaisesRegex(ValueError, "H3核验必须使用候选模型"):
                    load_model_settings(env_path)

    def test_requires_complete_user_h3_confirmation(self) -> None:
        frozen = {
            "status": "h3_frozen_user_confirmed",
            "h3_confirmation": {
                "model_and_calling_method": True,
                "prompt_v1": True,
                "schema_v1": True,
                "comparison_policy_version": "v2",
                "dataset_annotation_consistency_layer": True,
                "diagnostic_hints_do_not_auto_judge": True,
                "final_reference_accuracy_gate": True,
            },
        }
        require_h3_frozen(frozen)
        with self.assertRaisesRegex(ValueError, "H3尚未由用户确认"):
            require_h3_frozen({"status": "pending"})
        incomplete = {
            "status": "h3_frozen_user_confirmed",
            "h3_confirmation": {"prompt_v1": True},
        }
        with self.assertRaisesRegex(ValueError, "H3确认记录不完整"):
            require_h3_frozen(incomplete)

    def test_current_candidate_has_complete_h3_v2_confirmation(self) -> None:
        candidate = load_model_candidate()

        self.assertEqual(
            candidate["status"],
            "h3_frozen_user_confirmed",
        )
        self.assertEqual(
            candidate["h3_confirmation"][
                "final_reference_accuracy_gate_scope"
            ],
            "main_sample_only",
        )
        self.assertFalse(
            candidate["h3_confirmation"]["fixed_validation_reference_gate"]
        )
        require_h3_frozen(candidate)


if __name__ == "__main__":
    unittest.main()
