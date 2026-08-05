from __future__ import annotations

import unittest
from copy import deepcopy

from src.q01_q10_acceptance_harness_revision_design import (
    AcceptanceHarnessRevisionDesignError,
    compile_revision_design_preview,
    load_acceptance_harness_revision_design,
    validate_acceptance_harness_revision_design,
)


class Q01Q10AcceptanceHarnessRevisionDesignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.preview = compile_revision_design_preview()

    def test_preview_is_design_only_and_keeps_sources_unchanged(self) -> None:
        self.assertEqual(
            self.preview.status,
            "design_consistent_no_implementation",
        )
        self.assertTrue(self.preview.source_files_unchanged)
        self.assertFalse(self.preview.implementation_performed)
        self.assertFalse(self.preview.real_model_called)
        self.assertFalse(self.preview.network_used)
        self.assertFalse(self.preview.api_key_read)

    def test_completeness_manifest_matches_frozen_h2_leaves(self) -> None:
        self.assertEqual(
            self.preview.manifest_leaf_counts,
            {
                "Q01": 7,
                "Q02": 27,
                "Q03": 23,
                "Q04": 7,
                "Q05": 14,
                "Q06": 20,
                "Q07": 12,
            },
        )

    def test_request_examples_are_explicit_program_sources(self) -> None:
        self.assertEqual(
            self.preview.request_record_examples,
            (
                {
                    "question_id": "Q02",
                    "parameter_name": "top_n",
                    "value": "5",
                },
                {
                    "question_id": "Q03",
                    "parameter_name": "top_n",
                    "value": "5",
                },
                {
                    "question_id": "Q04",
                    "parameter_name": "excluded_period",
                    "value": "2011-12",
                },
                {
                    "question_id": "Q06",
                    "parameter_name": "top_n",
                    "value": "3",
                },
            ),
        )

    def test_rank_preview_reproduces_current_ambiguity(self) -> None:
        historical = {"Q02": 10, "Q03": 10, "Q06": 6}
        self.assertEqual(
            self.preview.current_ambiguous_rank_counts,
            {"Q02": 0, "Q03": 0, "Q06": 0},
        )
        self.assertEqual(
            self.preview.historical_ambiguous_rank_counts,
            historical,
        )
        self.assertEqual(
            self.preview.preview_rank_values_cleared,
            historical,
        )
        self.assertEqual(
            self.preview.selected_rank_route,
            "rank_only_on_selected_metric_fact",
        )

    def test_semantic_mock_and_control_routes_are_separated(self) -> None:
        self.assertEqual(
            self.preview.semantic_plain_significant_route,
            "human_review",
        )
        self.assertEqual(
            self.preview.semantic_product_classification_route,
            "human_review",
        )
        self.assertEqual(len(self.preview.mock_status_dimensions), 6)
        self.assertEqual(
            self.preview.q10_candidate_boundary_codes,
            (
                "forecasting_unsupported",
                "automatic_replenishment_unsupported",
            ),
        )

    def test_contract_rejects_implementation_or_scope_expansion(self) -> None:
        contract = validate_acceptance_harness_revision_design()
        self.assertEqual(
            contract["status"],
            "frozen_by_user_offline_validated_not_implemented",
        )
        self.assertTrue(
            contract["authorization"]["design_frozen_by_user"]
        )
        self.assertFalse(
            contract["authorization"]["candidate_is_not_frozen"]
        )
        for section, field in (
            ("authorization", "implementation_allowed"),
            ("scope", "h2_reference_answers_changed"),
            ("scope", "v2_2_3_resumed"),
            ("scope", "real_model_calls_allowed"),
        ):
            changed = deepcopy(
                load_acceptance_harness_revision_design()
            )
            changed[section][field] = True
            with self.subTest(section=section, field=field):
                with self.assertRaises(
                    AcceptanceHarnessRevisionDesignError
                ):
                    validate_acceptance_harness_revision_design(changed)

    def test_freeze_does_not_authorize_implementation_or_real_calls(
        self,
    ) -> None:
        contract = validate_acceptance_harness_revision_design()
        freeze = contract["user_freeze"]
        self.assertEqual(len(freeze["frozen_boundaries"]), 6)
        self.assertTrue(
            freeze["freeze_does_not_authorize_implementation"]
        )
        self.assertTrue(
            freeze["freeze_does_not_authorize_real_model_calls"]
        )
        self.assertTrue(
            freeze["h2_reference_answers_remain_frozen_unchanged"]
        )
        self.assertTrue(freeze["v2_2_3_remains_paused"])

    def test_contract_rejects_six_boundary_policy_drift(self) -> None:
        probes = []

        rank = deepcopy(load_acceptance_harness_revision_design())
        rank["boundary_3_rank_semantics"][
            "new_rank_metric_field_required"
        ] = True
        probes.append(rank)

        semantic = deepcopy(load_acceptance_harness_revision_design())
        semantic["boundary_4_semantic_rules"][
            "plain_significant_is_not_statistical_hard_fail"
        ] = False
        probes.append(semantic)

        mock = deepcopy(load_acceptance_harness_revision_design())
        mock["boundary_5_mock_responsibility"][
            "current_generic_mock_report_may_pass_content_acceptance"
        ] = True
        probes.append(mock)

        q10 = deepcopy(load_acceptance_harness_revision_design())
        q10["boundary_6_control_content"]["Q10"][
            "future_control_schema_addition"
        ]["enum_values"] = ["forecasting_unsupported"]
        probes.append(q10)

        for index, changed in enumerate(probes, start=1):
            with self.subTest(probe=index):
                with self.assertRaises(
                    AcceptanceHarnessRevisionDesignError
                ):
                    validate_acceptance_harness_revision_design(changed)


if __name__ == "__main__":
    unittest.main()
