from __future__ import annotations

import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class StreamlitAppTests(unittest.TestCase):
    def test_initial_render_has_two_tabs_and_does_not_raise(self) -> None:
        results_dir = PROJECT_ROOT / "results"
        before = {
            path.relative_to(results_dir)
            for path in results_dir.rglob("*.json")
        }
        app = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run(timeout=20)
        after = {
            path.relative_to(results_dir)
            for path in results_dir.rglob("*.json")
        }
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(
            [tab.label for tab in app.tabs],
            ["单张表单识别", "验证结果"],
        )
        self.assertIn("运行单张识别", [button.label for button in app.button])
        self.assertIn("运行固定验证", [button.label for button in app.button])
        single_button = next(
            button
            for button in app.button
            if button.label == "运行单张识别"
        )
        validation_button = next(
            button
            for button in app.button
            if button.label == "运行固定验证"
        )
        self.assertFalse(single_button.disabled)
        self.assertFalse(validation_button.disabled)
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
