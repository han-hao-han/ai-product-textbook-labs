from __future__ import annotations

import json
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = PROJECT_ROOT / "schemas" / "sample_review_record_v1.json"


class SampleReviewSchemaTests(unittest.TestCase):
    def test_schema_declares_auditable_privacy_and_annotation_sections(self) -> None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

        self.assertEqual(
            schema["$schema"],
            "https://json-schema.org/draft/2020-12/schema",
        )
        self.assertIn("privacy_review", schema["required"])
        self.assertIn("annotation_review", schema["required"])
        self.assertIn("final_reference_status", schema["required"])
        privacy = schema["properties"]["privacy_review"]["properties"]
        self.assertEqual(
            privacy["national_id"]["enum"],
            ["not_reviewed", "not_present", "present", "uncertain"],
        )
        correction = schema["$defs"]["correction"]["properties"]
        self.assertIn("reason", correction)
        self.assertIn("evidence", correction)
        annotation = schema["properties"]["annotation_review"]
        self.assertIn("special_symbol_review", annotation["required"])
        policy = annotation["properties"]["special_symbol_review"]["properties"]
        self.assertEqual(
            policy["interpretation_policy"]["const"],
            "preserve_glyphs_no_automatic_semantic_equivalence",
        )


if __name__ == "__main__":
    unittest.main()
