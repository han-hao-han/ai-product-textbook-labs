from __future__ import annotations

import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class H4StreamlitAppTests(unittest.TestCase):
    def test_initial_render_has_no_exception_and_does_not_call_model(self) -> None:
        app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=30).run()
        self.assertEqual(list(app.exception), [])
        self.assertEqual(
            app.title[0].value,
            "1.5.6 基于真实零售数据的经营分析 Agent",
        )
        self.assertEqual(
            [tab.label for tab in app.tabs],
            ["💬 对话分析", "📊 数据与口径", "🧪 教学验收", "📦 运行记录"],
        )
        self.assertIn("API Key", " ".join(item.value for item in app.caption))


if __name__ == "__main__":
    unittest.main()
