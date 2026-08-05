from __future__ import annotations

import unittest

from scripts.validate_retail_tools import run_validation
from src.h2_reference_answers import build_h2_reference_answers
from src.retail_cleaning import build_retail_data_layers
from src.retail_tools import RetailToolService
from src.tool_registry import RetailToolRegistry
from tests.test_retail_cleaning import sample_frame


class ToolValidationTests(unittest.TestCase):
    def test_q01_to_q07_match_deterministic_reference(self) -> None:
        layers = build_retail_data_layers(sample_frame())
        registry = RetailToolRegistry(RetailToolService(layers))
        reference = build_h2_reference_answers(layers)["answers"]

        report = run_validation(registry, reference)

        self.assertEqual(report["summary"]["case_count"], 7)
        self.assertEqual(report["summary"]["failed"], 0)
        self.assertTrue(report["summary"]["all_passed"])
        self.assertFalse(
            report["privacy"]["customer_id_values_exported"]
        )


if __name__ == "__main__":
    unittest.main()
