from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.export_session_record_contract import build_contract


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = (
    PROJECT_ROOT
    / "config"
    / "h3_session_record_contract.json"
)


class SessionRecordContractTests(unittest.TestCase):
    def test_checked_in_contract_matches_schema_source(self) -> None:
        checked_in = json.loads(
            CONTRACT_PATH.read_text(encoding="utf-8")
        )

        self.assertEqual(checked_in, build_contract())

    def test_frozen_contract_preserves_session_and_offline_boundaries(
        self,
    ) -> None:
        contract = build_contract()

        self.assertEqual(contract["status"], "frozen_by_user")
        self.assertFalse(
            contract["multi_turn"]["historical_reports_merged"]
        )
        self.assertTrue(
            contract["offline_mode"][
                "must_not_claim_agent_behavior"
            ]
        )
        self.assertFalse(
            contract["export_and_import"][
                "overwrite_existing_files"
            ]
        )
        self.assertEqual(
            contract["export_and_import"]["file_count"],
            4,
        )
        extension = contract["v2_2_2_additive_extension"]
        self.assertTrue(
            extension["run_record_retains_manual_review_flags"]
        )
        self.assertFalse(extension["existing_run_record_fields_changed"])
        self.assertFalse(extension["model_control_schema_changed"])


if __name__ == "__main__":
    unittest.main()
