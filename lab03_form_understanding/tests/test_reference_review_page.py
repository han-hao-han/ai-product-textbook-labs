from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.reference_review_page import write_reference_review_page


class ReferenceReviewPageTests(unittest.TestCase):
    def test_page_preserves_rows_symbols_and_uses_relative_image_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "raw" / "sample.jpg"
            image_path.parent.mkdir()
            image_path.write_bytes(b"fake")
            output_path = write_reference_review_page(
                sample_id="sample-1",
                document=_document(),
                image_path=image_path,
                review_record=_review(),
                output_dir=root / "local",
            )

            content = output_path.read_text(encoding="utf-8")
            self.assertIn("☑是 □否", content)
            self.assertIn("同名字段共2项", content)
            self.assertIn("Q:1", content)
            self.assertIn("../raw/sample.jpg", content)
            self.assertNotIn(str(root), content)
            self.assertIn("不会自动保存", content)
            self.assertIn("已记录校正：replace_value", content)
            self.assertIn("已记录结构：table-1 / row-1 / 第1列", content)


def _document() -> dict:
    return {
        "id": "sample-1",
        "img": {"fname": "sample.jpg"},
        "document": [
            {
                "id": 1,
                "text": "选项",
                "label": "question",
                "linking": [[1, 2]],
                "words": [],
            },
            {
                "id": 2,
                "text": "☑是 □否",
                "label": "answer",
                "linking": [[1, 2]],
                "words": [],
            },
            {
                "id": 3,
                "text": "选项",
                "label": "question",
                "linking": [[3, 4]],
                "words": [],
            },
            {
                "id": 4,
                "text": "第二行",
                "label": "answer",
                "linking": [[3, 4]],
                "words": [],
            },
        ],
    }


def _review() -> dict:
    return {
        "sample_id": "sample-1",
        "annotation_review": {
            "status": "pending",
            "corrections": [
                {
                    "correction_id": "c-1",
                    "action": "replace_value",
                    "source_question_entity_id": 1,
                    "source_answer_entity_id": 2,
                }
            ],
            "structure_reviews": [
                {
                    "review_id": "table-1",
                    "rows": [
                        {
                            "row_id": "row-1",
                            "cells": [
                                {
                                    "column_index": 1,
                                    "source_question_entity_id": 1,
                                    "source_answer_entity_id": 2,
                                }
                            ],
                        }
                    ],
                }
            ],
        },
        "final_reference_status": "not_ready",
    }


if __name__ == "__main__":
    unittest.main()
