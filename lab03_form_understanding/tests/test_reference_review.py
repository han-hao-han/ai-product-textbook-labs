from __future__ import annotations

import unittest

from src.reference_review import ReferenceReviewError, build_final_reference


class ReferenceReviewTests(unittest.TestCase):
    def test_not_ready_withholds_final_reference(self) -> None:
        result = build_final_reference(_fields(), _review("not_ready", "pending"))

        self.assertFalse(result["available_for_accuracy"])
        self.assertIsNone(result["final_reference_fields"])

    def test_pending_corrections_are_validated_and_previewed_only(self) -> None:
        review = _review("not_ready", "pending")
        review["annotation_review"]["corrections"] = [
            {
                "correction_id": "c-1",
                "action": "replace_value",
                "source_question_entity_id": 1,
                "source_answer_entity_id": 2,
                "original": {"key": "姓名", "value": "张山"},
                "corrected": {"key": "姓名", "value": "张三"},
                "reason": "已记录但尚未完成全样本复核",
                "evidence": "visible_image",
            }
        ]

        result = build_final_reference(_fields(), review)

        self.assertFalse(result["available_for_accuracy"])
        self.assertIsNone(result["final_reference_fields"])
        self.assertEqual(result["recorded_correction_ids"], ["c-1"])
        self.assertEqual(result["correction_preview_field_count"], 1)

    def test_confirmed_source_annotation_is_available(self) -> None:
        result = build_final_reference(
            _fields(), _review("source_annotation_confirmed", "confirmed")
        )

        self.assertTrue(result["available_for_accuracy"])
        self.assertEqual(result["final_reference_fields"], _fields())

    def test_correction_is_applied_without_mutating_source(self) -> None:
        source = _fields()
        review = _review("human_corrected", "corrected")
        review["annotation_review"]["corrections"] = [
            {
                "correction_id": "c-1",
                "action": "replace_value",
                "source_question_entity_id": 1,
                "source_answer_entity_id": 2,
                "original": {"key": "姓名", "value": "张山"},
                "corrected": {"key": "姓名", "value": "张三"},
                "reason": "原图显示为张三",
                "evidence": "visible_image",
            }
        ]

        result = build_final_reference(source, review)

        self.assertEqual(source[0]["value"], "张山")
        self.assertEqual(result["final_reference_fields"][0]["value"], "张三")
        self.assertEqual(result["applied_correction_ids"], ["c-1"])

    def test_stale_correction_is_rejected(self) -> None:
        review = _review("human_corrected", "corrected")
        review["annotation_review"]["corrections"] = [
            {
                "correction_id": "c-1",
                "action": "replace_value",
                "source_question_entity_id": 1,
                "source_answer_entity_id": 2,
                "original": {"key": "姓名", "value": "不是当前值"},
                "corrected": {"key": "姓名", "value": "张三"},
                "reason": "测试陈旧校正",
                "evidence": "visible_image",
            }
        ]

        with self.assertRaisesRegex(ReferenceReviewError, "original"):
            build_final_reference(_fields(), review)

    def test_table_structure_is_attached_by_entity_ids(self) -> None:
        review = _review("source_annotation_confirmed", "confirmed")
        review["annotation_review"]["structure_reviews"] = [
            {
                "review_id": "table-1",
                "structure_type": "table",
                "source_field_indices": [1],
                "row_count": 1,
                "column_count": 1,
                "columns": ["姓名"],
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
                "decision": "preserve_fields_with_row_grouping",
                "reason": "原图为一行一列表格",
                "evidence": "visible_image",
            }
        ]

        result = build_final_reference(_fields(), review)

        field = result["final_reference_fields"][0]
        self.assertEqual(field["structure_group_id"], "table-1")
        self.assertEqual(field["structure_row_id"], "row-1")
        self.assertEqual(field["structure_column_index"], 1)

    def test_post_run_adjudication_cannot_claim_formal_validation(self) -> None:
        review = _review("source_annotation_confirmed", "confirmed")
        review["evaluation_context"] = {
            "reference_frozen_before_model_run": False,
            "model_run_id": "run-1",
            "adjudicated_at": "2026-07-23T00:00:00Z",
            "usage": "teaching_post_run_adjudication_only",
            "included_in_formal_validation": True,
            "notes": "无效测试状态",
        }

        with self.assertRaisesRegex(ReferenceReviewError, "正式验证"):
            build_final_reference(_fields(), review)


def _fields() -> list[dict]:
    return [
        {
            "key": "姓名",
            "value": "张山",
            "question_entity_id": 1,
            "answer_entity_id": 2,
        }
    ]


def _review(final_status: str, annotation_status: str) -> dict:
    return {
        "schema_version": "sample-review-v1",
        "sample_id": "sample-1",
        "dataset": "XFUND v1.0 zh",
        "privacy_review": {
            "status": "passed",
            "national_id": "not_present",
        },
        "annotation_review": {
            "status": annotation_status,
            "corrections": [],
        },
        "final_reference_status": final_status,
    }


if __name__ == "__main__":
    unittest.main()
