from __future__ import annotations

import unittest

from src.privacy_screening import screen_document_privacy


class PrivacyScreeningTests(unittest.TestCase):
    def test_hard_excludes_national_id_without_storing_literal(self) -> None:
        document = _document(
            [
                ("身份证号码", "question"),
                ("120113198503113746", "answer"),
            ]
        )

        result = screen_document_privacy(document)

        self.assertTrue(result["hard_excluded"])
        self.assertIn("national_id_value", result["hard_exclusion_reasons"])
        self.assertIn("national_id", result["signal_categories"])
        self.assertNotIn("120113198503113746", str(result))
        self.assertFalse(result["matched_literals_stored"])

    def test_blank_national_id_field_requires_review_but_is_not_hard_excluded(self) -> None:
        result = screen_document_privacy(
            _document([("身份证号码", "question"), ("", "answer")])
        )

        self.assertFalse(result["hard_excluded"])
        self.assertIn("national_id_field", result["signal_categories"])

    def test_hard_excludes_masked_national_id(self) -> None:
        result = screen_document_privacy(
            _document([("证件号码", "question"), ("120113********374X", "answer")])
        )

        self.assertTrue(result["hard_excluded"])
        self.assertIn("national_id_value", result["hard_exclusion_reasons"])
        self.assertNotIn("120113", str(result))

    def test_flags_phone_and_email_without_retaining_values(self) -> None:
        document = _document(
            [
                ("联系电话", "question"),
                ("13812345678", "answer"),
                ("邮箱", "question"),
                ("reader@example.com", "answer"),
            ]
        )

        result = screen_document_privacy(document)

        self.assertFalse(result["hard_excluded"])
        self.assertIn("phone", result["signal_categories"])
        self.assertIn("email", result["signal_categories"])
        self.assertNotIn("13812345678", str(result))
        self.assertNotIn("reader@example.com", str(result))

    def test_benign_document_has_no_detected_signals(self) -> None:
        result = screen_document_privacy(
            _document([("产品名称", "question"), ("教学设备", "answer")])
        )

        self.assertFalse(result["hard_excluded"])
        self.assertEqual(result["risk_score"], 0)
        self.assertEqual(result["signal_categories"], [])

    def test_flags_person_role_and_bank_context(self) -> None:
        result = screen_document_privacy(
            _document(
                [
                    ("项目负责人", "question"),
                    ("某人", "answer"),
                    ("开户许可证编号", "question"),
                    ("DEMO-001", "answer"),
                ]
            )
        )

        self.assertFalse(result["hard_excluded"])
        self.assertIn("person_identity", result["signal_categories"])
        self.assertIn("financial_or_account", result["signal_categories"])

    def test_flags_interviewer_as_person_identity_context(self) -> None:
        result = screen_document_privacy(
            _document([("面试官", "question"), ("某人", "answer")])
        )

        self.assertIn("person_identity", result["signal_categories"])


def _document(items: list[tuple[str, str]]) -> dict:
    return {
        "id": "mock",
        "img": {"fname": "mock.png"},
        "document": [
            {
                "id": index,
                "text": text,
                "label": label,
                "linking": [],
                "words": [],
            }
            for index, (text, label) in enumerate(items, start=1)
        ],
    }


if __name__ == "__main__":
    unittest.main()
