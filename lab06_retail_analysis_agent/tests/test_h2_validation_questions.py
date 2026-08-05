from __future__ import annotations

import json
import unittest
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
QUESTION_PATH = (
    PROJECT_ROOT
    / "config"
    / "h2_validation_questions.json"
)
LOCAL_ANSWER_PATH = (
    PROJECT_ROOT / "data" / "raw" / "h2_reference_answers.json"
)


class H2ValidationQuestionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.question_set = json.loads(
            QUESTION_PATH.read_text(encoding="utf-8")
        )

    def test_question_composition_matches_task_contract(self) -> None:
        questions = self.question_set["questions"]
        counts = Counter(item["type"] for item in questions)

        self.assertEqual(
            self.question_set["status"],
            "frozen_by_user",
        )
        self.assertEqual(len(questions), 10)
        self.assertEqual(counts["single_tool"], 4)
        self.assertEqual(counts["multi_tool"], 3)
        self.assertEqual(counts["clarification"], 1)
        self.assertEqual(counts["capability_boundary"], 2)

    def test_every_question_contains_required_review_fields(self) -> None:
        required = {
            "id",
            "type",
            "question",
            "examines",
            "necessary_background",
            "reference_answer",
            "expected_behavior",
            "allowed_reasonable_calls",
            "prohibited_behavior",
            "manual_checklist",
        }
        for question in self.question_set["questions"]:
            with self.subTest(question=question["id"]):
                self.assertTrue(required.issubset(question))
                self.assertTrue(question["manual_checklist"])
                self.assertTrue(question["prohibited_behavior"])

    def test_question_set_does_not_expose_customer_ids(self) -> None:
        serialized = json.dumps(
            self.question_set,
            ensure_ascii=False,
        )

        self.assertNotRegex(serialized, r"\b\d{5}\.0\b")
        self.assertNotIn('"customer_id":', serialized.casefold())

    def test_frozen_answers_match_local_real_run_when_available(
        self,
    ) -> None:
        if not LOCAL_ANSWER_PATH.exists():
            self.skipTest("本地真实参考答案不存在。")
        local_answers = json.loads(
            LOCAL_ANSWER_PATH.read_text(encoding="utf-8")
        )["answers"]

        for question in self.question_set["questions"]:
            with self.subTest(question=question["id"]):
                self.assertEqual(
                    question["reference_answer"],
                    local_answers[question["id"]],
                )


if __name__ == "__main__":
    unittest.main()
