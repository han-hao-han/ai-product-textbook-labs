from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.deepseek_report_terminal_serialization_v2_3 import (
    run_offline_validation,
    validate_design,
)


class DeepSeekReportTerminalSerializationV2_3FormalTests(unittest.TestCase):
    def test_design_and_full_offline_validation(self) -> None:
        self.assertEqual(
            validate_design()["selected_protocol"][
                "report_or_control_terminal_phase"
            ]["tools_visible"],
            0,
        )
        with tempfile.TemporaryDirectory() as temporary:
            summary = run_offline_validation(Path(temporary))
        self.assertEqual(summary["status"], "passed")
        self.assertEqual(summary["questions_passed"], 10)
        self.assertEqual(summary["total_model_responses"], 20)
        self.assertEqual(summary["standard_json_terminal_requests"], 10)
        self.assertEqual(summary["terminal_requests_with_tools"], 0)
        self.assertTrue(
            summary["saved_q02_probe"]["whole_response_rejected"]
        )
        self.assertFalse(summary["real_model_called"])


if __name__ == "__main__":
    unittest.main()
