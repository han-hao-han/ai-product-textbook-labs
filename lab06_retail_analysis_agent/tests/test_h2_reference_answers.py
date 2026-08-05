from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.h2_reference_answers import (  # noqa: E402
    build_h2_reference_answers,
)
from src.retail_cleaning import build_retail_data_layers  # noqa: E402
from tests.test_retail_cleaning import sample_frame  # noqa: E402


class H2ReferenceAnswerTests(unittest.TestCase):
    def test_answers_are_deterministic_and_private(self) -> None:
        layers = build_retail_data_layers(sample_frame())
        answers = build_h2_reference_answers(layers)

        self.assertEqual(
            answers["answers"]["Q01"]["sales_amount_gbp"],
            "4.47",
        )
        self.assertFalse(
            answers["basis"]["customer_id_values_exported"]
        )
        self.assertNotIn("12345", str(answers))

    def test_question_categories_have_expected_outcomes(self) -> None:
        answers = build_h2_reference_answers(
            build_retail_data_layers(sample_frame())
        )["answers"]

        self.assertEqual(len(answers), 10)
        self.assertEqual(
            answers["Q08"]["expected_outcome"],
            "clarify_once_before_tool_call",
        )
        self.assertEqual(
            answers["Q09"]["expected_outcome"],
            "refuse_unsupported_profit_analysis",
        )
        self.assertEqual(
            answers["Q10"]["expected_outcome"],
            "refuse_unsupported_forecast",
        )


if __name__ == "__main__":
    unittest.main()
