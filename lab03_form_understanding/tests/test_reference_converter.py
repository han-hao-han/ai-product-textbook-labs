from __future__ import annotations

import unittest

from src.reference_converter import convert_reference_fields


class ReferenceConverterTests(unittest.TestCase):
    def test_only_explicit_question_answer_relations_are_converted(self) -> None:
        document = {
            "id": "mock-001",
            "img": {"fname": "mock.png"},
            "document": [
                _entity(1, "姓名", "question", [[1, 2]]),
                _entity(2, "张三", "answer", [[1, 2]]),
                _entity(3, "申请表", "header", [[3, 4]]),
                _entity(4, "说明文字", "other", [[3, 4]]),
                _entity(5, "未关联字段", "question", []),
            ],
        }

        result = convert_reference_fields(document)

        self.assertEqual(result["sample_id"], "mock-001")
        self.assertEqual(
            result["reference_fields"],
            [
                {
                    "key": "姓名",
                    "value": "张三",
                    "question_entity_id": 1,
                    "answer_entity_id": 2,
                }
            ],
        )
        self.assertEqual(result["conversion_warnings"], [])

    def test_missing_relation_target_is_kept_as_warning(self) -> None:
        document = {
            "id": "mock-002",
            "img": {"fname": "mock.png"},
            "document": [_entity(1, "姓名", "question", [[1, 99]])],
        }

        result = convert_reference_fields(document)

        self.assertEqual(result["reference_fields"], [])
        self.assertIn("关系1-99指向不存在的实体", result["conversion_warnings"])

    def test_duplicate_links_do_not_duplicate_reference_fields(self) -> None:
        document = {
            "id": "mock-003",
            "img": {"fname": "mock.png"},
            "document": [
                _entity(1, "姓名", "question", [[1, 2], [2, 1]]),
                _entity(2, "张三", "answer", [[1, 2]]),
            ],
        }

        result = convert_reference_fields(document)

        self.assertEqual(len(result["reference_fields"]), 1)


def _entity(entity_id: int, text: str, label: str, linking: list[list[int]]) -> dict:
    return {
        "id": entity_id,
        "text": text,
        "label": label,
        "linking": linking,
        "words": [{"text": text, "box": [0, 0, 10, 10]}],
    }


if __name__ == "__main__":
    unittest.main()
