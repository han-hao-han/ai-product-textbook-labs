from __future__ import annotations

import re
import unittest

from scripts.run_fixed_questions_online import _session_id_for_run


class OnlineRunnerTests(unittest.TestCase):
    def test_timezone_plus_is_sanitized_for_session_schema(self) -> None:
        session_id = _session_id_for_run(
            "agent_online_20260731T132227_504780+0800"
        )

        self.assertEqual(
            session_id,
            "SESSION-agent_online_20260731T132227_504780_0800",
        )
        self.assertIsNotNone(
            re.fullmatch(r"SESSION-[A-Za-z0-9_-]+", session_id)
        )


if __name__ == "__main__":
    unittest.main()
