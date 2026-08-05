from __future__ import annotations

import unittest
from copy import deepcopy

from src.acceptance_harness_offline_validation import (
    AcceptanceHarnessImplementationError,
    load_acceptance_harness_implementation,
    run_acceptance_harness_implementation_verification,
    validate_acceptance_harness_implementation,
)


class AcceptanceHarnessOfflineValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = run_acceptance_harness_implementation_verification()

    def test_generic_and_complete_fixture_statuses_are_not_conflated(self) -> None:
        self.assertEqual(
            list(self.result.generic_mock_statuses.values())[:7],
            ["protocol_and_dataflow_passed"] * 7,
        )
        self.assertEqual(
            set(self.result.complete_fixture_statuses.values()),
            {"passed_deterministic_pending_manual_review"},
        )
        self.assertTrue(self.result.manifest_all_covered)

    def test_rank_provenance_and_control_boundaries_are_implemented(self) -> None:
        self.assertEqual(
            self.result.current_non_selected_metric_rank_counts,
            {"Q02": 0, "Q03": 0, "Q06": 0},
        )
        self.assertEqual(
            self.result.request_examples["Q06"],
            {
                "parameter_name": "top_n",
                "value": "3",
                "source": "validated_user_input",
            },
        )
        self.assertEqual(self.result.q09_wrong_alternative_status, "failed")
        self.assertEqual(self.result.q10_contradictory_status, "failed")

    def test_verification_is_offline_read_only_for_frozen_inputs(self) -> None:
        self.assertTrue(self.result.source_files_unchanged_during_verification)
        self.assertFalse(self.result.h2_reference_answers_changed)
        self.assertFalse(self.result.prompt_changed)
        self.assertFalse(self.result.v2_2_3_resumed)
        self.assertFalse(self.result.real_model_called)
        self.assertFalse(self.result.network_used)
        self.assertFalse(self.result.api_key_read)

    def test_contract_rejects_scope_or_boundary_drift(self) -> None:
        validate_acceptance_harness_implementation()
        mutations = []
        h2 = deepcopy(load_acceptance_harness_implementation())
        h2["scope"]["h2_reference_answers_changed"] = True
        mutations.append(h2)
        rank = deepcopy(load_acceptance_harness_implementation())
        rank["implementation"]["rank_route"] = "ambiguous"
        mutations.append(rank)
        real = deepcopy(load_acceptance_harness_implementation())
        real["scope"]["real_model_calls_allowed"] = True
        mutations.append(real)
        for index, changed in enumerate(mutations):
            with self.subTest(index=index):
                with self.assertRaises(AcceptanceHarnessImplementationError):
                    validate_acceptance_harness_implementation(changed)


if __name__ == "__main__":
    unittest.main()
