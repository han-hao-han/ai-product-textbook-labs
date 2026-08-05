from __future__ import annotations

import unittest
from copy import deepcopy

from src.native_tool_mainline_revision import (
    NativeToolMainlineRevisionError,
    load_native_tool_mainline_revision,
    validate_native_tool_mainline_revision,
)


class V2_1NativeToolMainlineRevisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.candidate = load_native_tool_mainline_revision()

    def test_mainline_candidate_passes_offline_contract_check(
        self,
    ) -> None:
        result = validate_native_tool_mainline_revision()

        self.assertEqual(result.status, "passed")
        self.assertEqual(result.tool_count, 7)
        self.assertTrue(result.model_selects_tool)
        self.assertTrue(result.model_generates_arguments)
        self.assertTrue(result.model_decides_continue)
        self.assertTrue(result.model_organizes_report)
        self.assertTrue(result.program_builds_charts)
        self.assertFalse(result.program_preselects_next_tool)
        self.assertFalse(result.real_model_calls_allowed)

    def test_recipe_cannot_be_restored_as_active_router(self) -> None:
        changed = deepcopy(self.candidate)
        changed["tool_validation_boundary"][
            "analysis_recipe_role"
        ]["active_router"] = True

        with self.assertRaises(NativeToolMainlineRevisionError):
            validate_native_tool_mainline_revision(changed)

    def test_program_cannot_preselect_tool_or_generate_arguments(
        self,
    ) -> None:
        preselected = deepcopy(self.candidate)
        preselected["native_tool_protocol"][
            "program_may_preselect_next_tool"
        ] = True
        with self.assertRaises(NativeToolMainlineRevisionError):
            validate_native_tool_mainline_revision(preselected)

        generated = deepcopy(self.candidate)
        generated["native_tool_protocol"][
            "program_may_generate_model_tool_arguments"
        ] = True
        with self.assertRaises(NativeToolMainlineRevisionError):
            validate_native_tool_mainline_revision(generated)

    def test_model_report_and_program_chart_roles_are_required(
        self,
    ) -> None:
        report_removed = deepcopy(self.candidate)
        report_removed["report_boundary"][
            "model_organizes_report"
        ] = False
        with self.assertRaises(NativeToolMainlineRevisionError):
            validate_native_tool_mainline_revision(report_removed)

        chart_removed = deepcopy(self.candidate)
        chart_removed["chart_boundary"][
            "program_builds_chart_data"
        ] = False
        with self.assertRaises(NativeToolMainlineRevisionError):
            validate_native_tool_mainline_revision(chart_removed)

    def test_q06_terminal_only_withdraws_tool_permission(self) -> None:
        terminal = self.candidate["report_boundary"][
            "q06_terminal_permission"
        ]
        self.assertEqual(terminal["tool_visibility"], 7)
        self.assertEqual(terminal["tool_choice"], "none")
        self.assertFalse(terminal["program_preselects_business_tool"])
        self.assertTrue(terminal["model_organizes_report"])

    def test_q06_requires_model_to_choose_both_tools(self) -> None:
        flow = self.candidate["dependent_call_boundary"][
            "required_behavior"
        ]
        joined = "\n".join(flow)

        self.assertIn(
            "模型第一步原生选择analyze_time_trend",
            joined,
        )
        self.assertIn(
            "模型决定继续并原生选择rank_products",
            joined,
        )
        self.assertFalse(
            self.candidate["q06_reference_flow"][
                "program_does_not_preselect_tools"
            ]
            is False
        )

    def test_old_real_validation_plan_is_paused(self) -> None:
        validation = self.candidate["real_validation"]

        self.assertEqual(
            validation["previous_plan_status"],
            "paused_after_mainline_boundaries_reopened",
        )
        self.assertFalse(validation["real_model_calls_allowed"])
        self.assertEqual(
            validation[
                "provisional_expected_response_count_if_all_pass"
            ],
            5,
        )


if __name__ == "__main__":
    unittest.main()
