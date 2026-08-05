from __future__ import annotations

import json
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
H2_METRIC_PATH = PROJECT_ROOT / "config" / "h2_metric_contract.json"
H2_QUESTION_PATH = (
    PROJECT_ROOT / "config" / "h2_validation_questions.json"
)
H3_CANDIDATE_PATH = (
    PROJECT_ROOT / "config" / "h3_technical_contract.candidate.json"
)


class H3TechnicalContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.h2_metric = json.loads(
            H2_METRIC_PATH.read_text(encoding="utf-8")
        )
        cls.h2_questions = json.loads(
            H2_QUESTION_PATH.read_text(encoding="utf-8")
        )
        cls.h3 = json.loads(
            H3_CANDIDATE_PATH.read_text(encoding="utf-8")
        )

    def test_h2_remains_frozen_while_h3_is_only_candidate(self) -> None:
        self.assertEqual(
            self.h2_metric["status"]["h2_overall"],
            "frozen",
        )
        self.assertEqual(
            self.h2_questions["status"],
            "frozen_by_user",
        )
        self.assertEqual(
            self.h3["status"],
            "candidate_pending_remaining_h3_validation_and_user_freeze",
        )

    def test_candidate_has_seven_bounded_tools(self) -> None:
        tools = self.h3["tool_registry_candidate"]

        self.assertEqual(len(tools), 7)
        self.assertEqual(len({item["name"] for item in tools}), 7)
        self.assertNotIn("python", str(tools).lower())
        self.assertNotIn("sql", str(tools).lower())
        self.assertNotIn("shell", str(tools).lower())

    def test_call_limits_and_schema_defense_are_explicit(self) -> None:
        limits = self.h3["tool_call_control_candidate"]
        schema = self.h3["strict_schema_rules_candidate"]

        self.assertEqual(limits["maximum_tool_calls_per_turn"], 4)
        self.assertEqual(
            limits["maximum_tool_calls_per_model_response"],
            1,
        )
        self.assertFalse(schema["additionalProperties"])
        self.assertTrue(schema["program_side_pydantic_validation"])

    def test_model_change_reopens_protocol_validation_without_h3_freeze(
        self,
    ) -> None:
        validation = self.h3["real_validation_plan"]

        self.assertFalse(validation["calls_are_not_yet_executed"])
        self.assertTrue(validation["calls_executed"])
        self.assertTrue(validation["all_passed"])
        self.assertEqual(validation["candidate_call_count"], 3)
        self.assertTrue(validation["historical_validation_only"])
        self.assertTrue(
            validation["does_not_validate_current_model"]
        )
        self.assertEqual(
            self.h3["recommended_provider"]["model"],
            "deepseek-v4-flash",
        )
        self.assertEqual(
            self.h3["recommended_provider"]["base_url"],
            "https://api.deepseek.com",
        )
        self.assertEqual(
            self.h3["recommended_provider"]["selection_status"],
            "selected_by_user_flash_terminal_boundary_offline_redesign",
        )
        self.assertEqual(
            self.h3["subgate_status"][
                "provider_base_url_model_protocol"
            ],
            "v2_2_2_formal_report_validator_integrated_offline_validated",
        )
        terminal_json = self.h3[
            "report_terminal_json_boundary_v2_2_1"
        ]
        self.assertEqual(
            terminal_json["status"],
            "frozen_by_user_pending_separate_real_authorization",
        )
        self.assertFalse(terminal_json["real_model_calls_allowed"])
        self.assertEqual(
            terminal_json["response_format_sequence"],
            [None, None, {"type": "json_object"}],
        )
        real_plan = self.h3[
            "q06_v2_2_1_flash_real_revalidation_plan"
        ]
        self.assertEqual(
            real_plan["status"],
            "frozen_real_validation_failed_pending_user_decision",
        )
        self.assertEqual(real_plan["response_attempt_upper_bound"], 3)
        self.assertEqual(real_plan["automatic_retry_count"], 0)
        self.assertTrue(real_plan["frozen_by_user"])
        self.assertFalse(real_plan["real_model_calls_allowed"])
        semantic = self.h3[
            "report_evidence_semantic_boundary_v2_2_2"
        ]
        self.assertEqual(
            semantic["status"],
            "frozen_by_user_formal_validator_integrated_offline_validated",
        )
        self.assertTrue(semantic["frozen_by_user"])
        self.assertTrue(semantic["formal_validator_integration_completed"])
        self.assertTrue(semantic["freeze_does_not_mark_q06_as_passed"])
        self.assertEqual(
            semantic["q01_q10_mock_regression_status"],
            "passed_10_of_10",
        )
        feedback = self.h3[
            "q06_report_revision_feedback_boundary_v2_2_3"
        ]
        self.assertEqual(
            feedback["status"],
            "paused_by_user_pending_q01_q10_acceptance_harness_audit",
        )
        self.assertTrue(feedback["paused_by_user"])
        self.assertFalse(feedback["candidate_revision_protocol_active"])
        self.assertEqual(feedback["existing_response_cap"], 3)
        self.assertEqual(feedback["future_candidate_response_cap"], 4)
        self.assertEqual(feedback["maximum_report_revision_responses"], 1)
        self.assertEqual(feedback["automatic_retry_count"], 0)
        self.assertFalse(feedback["real_model_calls_allowed"])
        audit = self.h3[
            "q01_q10_acceptance_harness_consistency_audit"
        ]
        self.assertEqual(
            audit["status"],
            "findings_accepted_six_boundaries_reopened_offline_design",
        )
        self.assertEqual(audit["finding_count"], 7)
        self.assertEqual(audit["p0_finding_count"], 0)
        self.assertTrue(audit["source_files_unchanged"])
        self.assertFalse(audit["v2_2_3_resumed"])
        self.assertFalse(audit["real_model_calls_allowed"])
        design = self.h3[
            "q01_q10_acceptance_harness_revision_design"
        ]
        self.assertEqual(
            design["status"],
            "frozen_by_user_offline_validated_not_implemented",
        )
        self.assertTrue(design["frozen_by_user"])
        self.assertTrue(
            design["freeze_does_not_authorize_implementation"]
        )
        self.assertEqual(len(design["six_boundaries"]), 6)
        self.assertEqual(
            design["provenance_source_types"],
            ["FACT", "REQUEST", "POLICY"],
        )
        self.assertEqual(
            design["rank_route"],
            "rank_only_on_selected_metric_fact",
        )
        self.assertEqual(design["negative_probe_passed"], 9)
        self.assertEqual(design["negative_probe_total"], 9)
        self.assertTrue(design["source_files_unchanged"])
        self.assertFalse(design["implementation_performed"])
        self.assertFalse(design["h2_reference_answers_changed"])
        self.assertFalse(design["v2_2_3_resumed"])
        self.assertFalse(design["real_model_calls_allowed"])
        self.assertEqual(
            self.h3["subgate_status"][
                "agent_orchestration_prompt_and_fixed_questions"
            ],
            "evidence_guard_prompt_offline_implemented_pending_separate_real_validation_authorization",
        )
        q02_implementation = self.h3[
            "q02_failure_harness_revision_implementation"
        ]
        self.assertEqual(
            q02_implementation["status"],
            "offline_implemented_saved_response_and_q01_q10_regression_completed_pending_prompt_boundary_decision",
        )
        self.assertTrue(q02_implementation["formal_report_is_empty"])
        self.assertFalse(q02_implementation["rejected_report_publishable"])
        self.assertFalse(
            q02_implementation["q02_chart_count_mismatch_present"]
        )
        consolidated = self.h3[
            "c1_q02_q01_q10_offline_consolidated_audit"
        ]
        self.assertEqual(
            consolidated["status"],
            "offline_audit_completed_pending_user_checkpoint",
        )
        self.assertEqual(
            consolidated["q02_primary_defect_owner"],
            "saved_model_report_content",
        )
        self.assertEqual(
            consolidated["q02_harness_cascade_defect"], "resolved"
        )
        self.assertTrue(
            consolidated["prompt_boundary_reopen_recommended"]
        )
        self.assertFalse(consolidated["real_model_called"])
        prompt_guard = self.h3[
            "native_report_prompt_evidence_guard_design"
        ]
        self.assertEqual(
            prompt_guard["status"],
            "frozen_by_user_offline_validated_implementation_authorized",
        )
        self.assertEqual(
            prompt_guard["candidate_rule_ids"],
            [
                "PROMPT-EVIDENCE-01",
                "PROMPT-EVIDENCE-02",
                "PROMPT-EVIDENCE-03",
            ],
        )
        self.assertTrue(prompt_guard["generic_not_q02_hardcoded"])
        self.assertTrue(prompt_guard["implementation_authorized"])
        self.assertFalse(prompt_guard["real_model_called"])
        prompt_implementation = self.h3[
            "native_report_prompt_evidence_guard_implementation"
        ]
        self.assertEqual(
            prompt_implementation["status"],
            "offline_implementation_and_full_regression_completed_pending_separate_real_validation_authorization",
        )
        self.assertEqual(
            prompt_implementation["q01_q10_offline_transport"],
            "passed_10_of_10",
        )
        self.assertEqual(
            prompt_implementation["offline_transport_request_contract"],
            {
                "auto_without_response_format": 19,
                "q06_none_with_json_object": 1,
                "status": "passed",
            },
        )
        self.assertFalse(prompt_implementation["real_model_called"])
        implementation = self.h3[
            "q01_q10_acceptance_harness_six_boundary_implementation"
        ]
        self.assertEqual(
            implementation["status"],
            "offline_implementation_validated_pending_user_checkpoint",
        )
        self.assertEqual(
            implementation["report_evidence_source_types"],
            ["FACT", "REQUEST", "POLICY"],
        )
        self.assertEqual(
            implementation["rank_ambiguity_counts_after_implementation"],
            {"Q02": 0, "Q03": 0, "Q06": 0},
        )
        self.assertEqual(implementation["negative_probe_passed"], 9)
        self.assertFalse(implementation["h2_reference_answers_changed"])
        self.assertFalse(implementation["v2_2_3_resumed"])
        self.assertFalse(implementation["real_model_calls_allowed"])
        flash_plan = self.h3[
            "q01_q10_new_harness_flash_real_validation_plan"
        ]
        self.assertEqual(
            flash_plan["status"],
            "frozen_by_user_pending_guarded_runner_design_and_separate_batch_authorization",
        )
        self.assertEqual(flash_plan["model"], "deepseek-v4-flash")
        self.assertEqual(
            flash_plan["batch_a"]["question_ids"],
            ["Q02", "Q06", "Q08", "Q09", "Q10"],
        )
        self.assertEqual(
            flash_plan["batch_a"]["maximum_response_attempts"], 8
        )
        self.assertEqual(
            flash_plan["batch_b"]["question_ids"],
            ["Q01", "Q03", "Q04", "Q05", "Q07"],
        )
        self.assertEqual(
            flash_plan["batch_b"]["maximum_response_attempts"], 12
        )
        self.assertEqual(
            flash_plan["all_questions_maximum_response_attempts"], 20
        )
        self.assertTrue(flash_plan["guarded_real_runner_implemented"])
        self.assertFalse(flash_plan["real_model_calls_allowed"])
        self.assertTrue(flash_plan["frozen_by_user"])
        self.assertTrue(
            flash_plan["freeze_does_not_authorize_runner_implementation"]
        )
        batch_a_runner = self.h3[
            "q01_q10_batch_a_safe_runner_implementation"
        ]
        self.assertEqual(
            batch_a_runner["status"],
            "offline_implementation_validated_pending_user_checkpoint",
        )
        self.assertEqual(batch_a_runner["response_attempt_upper_bound"], 8)
        self.assertEqual(batch_a_runner["automatic_retry_count"], 0)
        self.assertTrue(
            batch_a_runner["authorization_gate_blocked_before_api_key_read"]
        )
        self.assertEqual(batch_a_runner["success_actual_response_attempts"], 8)
        self.assertEqual(batch_a_runner["network_failure_count"], 1)
        self.assertTrue(
            batch_a_runner["ninth_attempt_blocked_before_underlying_client"]
        )
        self.assertFalse(batch_a_runner["real_model_calls_allowed"])
        real_authority = self.h3[
            "q01_q10_batch_a_real_authorization"
        ]
        self.assertEqual(
            real_authority["status"],
            "consumed_by_externally_interrupted_run",
        )
        self.assertEqual(real_authority["runner_exit_code"], 124)
        self.assertEqual(
            real_authority["actual_response_attempt_count"], "unknown"
        )
        self.assertFalse(real_authority["unused_attempt_capacity_reusable"])
        real_validation = self.h3[
            "q01_q10_batch_a_real_validation"
        ]
        self.assertEqual(
            real_validation["status"],
            "interrupted_by_outer_timeout_with_evidence_gap",
        )
        self.assertEqual(real_validation["saved_provider_responses"], 0)
        self.assertEqual(
            real_validation["real_model_result_status"],
            "unknown_not_accepted",
        )
        self.assertTrue(real_validation["authorization_consumed"])
        self.assertFalse(real_validation["additional_real_call_authorized"])
        crash_safe = self.h3[
            "q01_q10_batch_a_crash_safe_evidence_boundary"
        ]
        self.assertEqual(
            crash_safe["status"],
            "frozen_by_user_offline_validated_pending_new_real_authorization",
        )
        self.assertEqual(crash_safe["per_request_timeout_seconds"], 120)
        self.assertEqual(crash_safe["batch_internal_timeout_seconds"], 1080)
        self.assertEqual(
            crash_safe["success_recovery_counts"],
            {"reserved": 8, "http_received": 8, "parsed": 8},
        )
        self.assertTrue(crash_safe["deadline_stops_before_attempt"])
        self.assertFalse(crash_safe["automatic_resume_allowed"])
        self.assertTrue(crash_safe["frozen_by_user"])
        self.assertTrue(crash_safe["freeze_does_not_authorize_real_calls"])
        self.assertTrue(
            crash_safe["freeze_does_not_restore_consumed_authorization"]
        )
        self.assertFalse(crash_safe["real_model_calls_allowed"])
        self.assertEqual(semantic["current_numeric_issue_count"], 16)
        self.assertEqual(semantic["canonical_numeric_issue_count"], 1)
        self.assertEqual(semantic["deterministic_semantic_issue_count"], 7)
        self.assertEqual(semantic["manual_review_flag_count"], 8)
        self.assertFalse(semantic["real_model_calls_allowed"])
        self.assertEqual(
            self.h3["tool_layer_freeze"]["contract"],
            "config/h3_tool_contract.json",
        )
        self.assertEqual(
            self.h3["subgate_status"][
                "fact_chart_report_and_validation"
            ],
            "frozen",
        )
        self.assertEqual(
            self.h3["fact_chart_report_layer_freeze"]["contract"],
            "config/h3_fact_chart_report_contract.json",
        )
        self.assertEqual(
            self.h3["subgate_status"][
                "multi_turn_run_record_offline_and_export"
            ],
            "frozen",
        )
        self.assertEqual(
            self.h3["session_record_layer_freeze"]["contract"],
            "config/h3_session_record_contract.json",
        )
        self.assertEqual(
            self.h3["subgate_status"]["h3_overall"],
            "in_progress",
        )
        self.assertEqual(
            self.h3["status"],
            "candidate_pending_remaining_h3_validation_and_user_freeze",
        )

    def test_runtime_does_not_depend_on_openai_sdk(self) -> None:
        runtime = self.h3["runtime_candidates"]

        self.assertIn("httpx", runtime)
        self.assertNotIn("openai", runtime)


if __name__ == "__main__":
    unittest.main()
