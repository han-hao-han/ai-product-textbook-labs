from __future__ import annotations

import unittest

from src.session_logic import should_start_real_run, stored_result_for_input


class SessionLogicTests(unittest.TestCase):
    def test_rerender_does_not_start_a_call_without_button_event(self) -> None:
        self.assertFalse(
            should_start_real_run(
                button_clicked=False,
                confirmation_checked=True,
                currently_running=False,
            )
        )

    def test_requires_confirmation_and_not_already_running(self) -> None:
        self.assertFalse(
            should_start_real_run(
                button_clicked=True,
                confirmation_checked=False,
                currently_running=False,
            )
        )
        self.assertFalse(
            should_start_real_run(
                button_clicked=True,
                confirmation_checked=True,
                currently_running=True,
            )
        )
        self.assertTrue(
            should_start_real_run(
                button_clicked=True,
                confirmation_checked=True,
                currently_running=False,
            )
        )

    def test_does_not_show_another_inputs_saved_result(self) -> None:
        stored = {"input_id": "main", "payload": {"ok": True}}
        self.assertIs(stored_result_for_input(stored, "main"), stored)
        self.assertIsNone(stored_result_for_input(stored, "observation-1"))


if __name__ == "__main__":
    unittest.main()
