from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.export_tool_contract import build_contract


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOOL_CONTRACT_PATH = PROJECT_ROOT / "config" / "h3_tool_contract.json"


class ToolContractTests(unittest.TestCase):
    def test_checked_in_contract_matches_pydantic_source(self) -> None:
        checked_in = json.loads(
            TOOL_CONTRACT_PATH.read_text(encoding="utf-8")
        )

        self.assertEqual(checked_in, build_contract())

    def test_contract_is_frozen_and_has_no_executable_escape_hatch(
        self,
    ) -> None:
        contract = build_contract()
        policy = contract["execution_policy"]

        self.assertEqual(contract["status"], "frozen_by_user_request")
        self.assertEqual(len(contract["tools"]), 7)
        self.assertTrue(policy["whitelist_only"])
        self.assertFalse(
            policy["arbitrary_python_sql_shell_or_expression_allowed"]
        )


if __name__ == "__main__":
    unittest.main()
