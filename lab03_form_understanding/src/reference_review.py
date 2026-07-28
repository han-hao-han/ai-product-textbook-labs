from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any, Iterable


READY_FINAL_REFERENCE_STATUSES = (
    "source_annotation_confirmed",
    "human_corrected",
)

_CORRECTION_ACTIONS = (
    "add_field",
    "remove_field",
    "replace_key",
    "replace_value",
    "replace_pair",
    "repair_relation",
)


class ReferenceReviewError(ValueError):
    """An artificial review record is missing, stale, or internally inconsistent."""


def load_sample_review_record(
    review_records_dir: Path, sample_id: str
) -> dict[str, Any]:
    review_path = review_records_dir / f"{sample_id}.json"
    if not review_path.is_file():
        raise FileNotFoundError(f"找不到样本人工复核记录：{review_path}")
    try:
        with review_path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except json.JSONDecodeError as error:
        raise ReferenceReviewError("样本人工复核记录不是合法JSON") from error
    _validate_review_record(payload, expected_sample_id=sample_id)
    return payload


def build_final_reference(
    dataset_reference_fields: Iterable[dict[str, Any]],
    review_record: dict[str, Any] | None,
) -> dict[str, Any]:
    """Apply auditable human corrections without changing source annotations."""

    original_fields = [deepcopy(field) for field in dataset_reference_fields]
    if review_record is None:
        return {
            "status": "not_ready",
            "available_for_accuracy": False,
            "reason": "sample_review_record_not_loaded",
            "final_reference_fields": None,
            "applied_correction_ids": [],
            "evaluation_context": None,
        }

    _validate_review_record(
        review_record, expected_sample_id=str(review_record.get("sample_id", ""))
    )
    status = review_record["final_reference_status"]
    annotation_review = review_record["annotation_review"]
    corrections = annotation_review["corrections"]
    structure_reviews = annotation_review.get("structure_reviews", [])
    preview_fields = original_fields
    preview_applied_ids: list[str] = []
    if corrections:
        preview_fields, preview_applied_ids = _apply_corrections(
            original_fields, corrections
        )
    preview_fields = _apply_structure_reviews(
        preview_fields, structure_reviews
    )

    if status not in READY_FINAL_REFERENCE_STATUSES:
        return {
            "status": status,
            "available_for_accuracy": False,
            "reason": (
                "annotation_review_rejected"
                if status == "rejected"
                else "annotation_review_not_ready"
            ),
            "final_reference_fields": None,
            "applied_correction_ids": [],
            "recorded_correction_ids": preview_applied_ids,
            "correction_preview_field_count": len(preview_fields),
            "evaluation_context": review_record.get("evaluation_context"),
        }

    if review_record["privacy_review"]["status"] != "passed":
        raise ReferenceReviewError("最终参考结果要求隐私复核状态为passed")
    if review_record["privacy_review"]["national_id"] != "not_present":
        raise ReferenceReviewError("最终参考结果要求人工确认未出现身份证号码")

    if status == "source_annotation_confirmed":
        if annotation_review["status"] != "confirmed":
            raise ReferenceReviewError(
                "source_annotation_confirmed要求annotation_review.status为confirmed"
            )
        if corrections:
            raise ReferenceReviewError("确认原标注时corrections必须为空")
        final_fields = _apply_structure_reviews(
            original_fields, structure_reviews
        )
        applied_ids: list[str] = []
    else:
        if annotation_review["status"] != "corrected":
            raise ReferenceReviewError(
                "human_corrected要求annotation_review.status为corrected"
            )
        if not corrections:
            raise ReferenceReviewError("human_corrected至少需要一条人工校正")
        final_fields = preview_fields
        applied_ids = preview_applied_ids

    return {
        "status": status,
        "available_for_accuracy": True,
        "reason": None,
        "final_reference_fields": final_fields,
        "applied_correction_ids": applied_ids,
        "recorded_correction_ids": applied_ids,
        "correction_preview_field_count": len(final_fields),
        "evaluation_context": review_record.get("evaluation_context"),
    }


def _validate_review_record(
    payload: Any, *, expected_sample_id: str
) -> None:
    if not isinstance(payload, dict):
        raise ReferenceReviewError("样本人工复核记录顶层必须是对象")
    if payload.get("schema_version") != "sample-review-v1":
        raise ReferenceReviewError("样本人工复核记录版本必须为sample-review-v1")
    if payload.get("sample_id") != expected_sample_id:
        raise ReferenceReviewError("样本人工复核记录的sample_id不一致")
    if payload.get("dataset") != "XFUND v1.0 zh":
        raise ReferenceReviewError("样本人工复核记录的数据集标识不正确")

    privacy_review = payload.get("privacy_review")
    annotation_review = payload.get("annotation_review")
    if not isinstance(privacy_review, dict) or not isinstance(
        annotation_review, dict
    ):
        raise ReferenceReviewError("样本人工复核记录缺少隐私或标注复核对象")
    if privacy_review.get("status") not in ("pending", "passed", "rejected"):
        raise ReferenceReviewError("隐私复核状态无效")
    if privacy_review.get("national_id") not in (
        "not_reviewed",
        "not_present",
        "present",
        "uncertain",
    ):
        raise ReferenceReviewError("身份证号码复核状态无效")
    if annotation_review.get("status") not in (
        "pending",
        "confirmed",
        "corrected",
        "rejected",
    ):
        raise ReferenceReviewError("标注复核状态无效")
    corrections = annotation_review.get("corrections")
    if not isinstance(corrections, list):
        raise ReferenceReviewError("corrections必须是数组")
    structure_reviews = annotation_review.get("structure_reviews", [])
    if not isinstance(structure_reviews, list):
        raise ReferenceReviewError("structure_reviews必须是数组")

    final_status = payload.get("final_reference_status")
    if final_status not in (
        "not_ready",
        "source_annotation_confirmed",
        "human_corrected",
        "rejected",
    ):
        raise ReferenceReviewError("最终参考结果状态无效")
    evaluation_context = payload.get("evaluation_context")
    if evaluation_context is not None:
        _validate_evaluation_context(evaluation_context)

    correction_ids: set[str] = set()
    for correction in corrections:
        _validate_correction(correction)
        correction_id = correction["correction_id"]
        if correction_id in correction_ids:
            raise ReferenceReviewError(f"校正ID重复：{correction_id}")
        correction_ids.add(correction_id)
    structure_review_ids: set[str] = set()
    for structure_review in structure_reviews:
        _validate_structure_review(structure_review)
        review_id = structure_review["review_id"]
        if review_id in structure_review_ids:
            raise ReferenceReviewError(f"结构复核ID重复：{review_id}")
        structure_review_ids.add(review_id)


def _validate_correction(correction: Any) -> None:
    if not isinstance(correction, dict):
        raise ReferenceReviewError("每项人工校正必须是对象")
    correction_id = correction.get("correction_id")
    action = correction.get("action")
    if not isinstance(correction_id, str) or not correction_id.strip():
        raise ReferenceReviewError("人工校正缺少correction_id")
    if action not in _CORRECTION_ACTIONS:
        raise ReferenceReviewError(f"不支持的人工校正操作：{action}")
    if not isinstance(correction.get("reason"), str) or not correction[
        "reason"
    ].strip():
        raise ReferenceReviewError(f"校正{correction_id}缺少原因")
    if correction.get("evidence") not in (
        "visible_image",
        "source_annotation",
        "both",
    ):
        raise ReferenceReviewError(f"校正{correction_id}的evidence无效")
    for field_name in ("original", "corrected"):
        field = correction.get(field_name)
        if field is not None and (
            not isinstance(field, dict)
            or not isinstance(field.get("key"), str)
            or not isinstance(field.get("value"), str)
        ):
            raise ReferenceReviewError(
                f"校正{correction_id}的{field_name}必须是键值对象或null"
            )


def _validate_structure_review(structure_review: Any) -> None:
    if not isinstance(structure_review, dict):
        raise ReferenceReviewError("每项结构复核必须是对象")
    review_id = structure_review.get("review_id")
    if not isinstance(review_id, str) or not review_id.strip():
        raise ReferenceReviewError("结构复核缺少review_id")
    if structure_review.get("structure_type") != "table":
        raise ReferenceReviewError(f"结构复核{review_id}只支持table")
    if structure_review.get("decision") != "preserve_fields_with_row_grouping":
        raise ReferenceReviewError(f"结构复核{review_id}的decision无效")
    if structure_review.get("evidence") != "visible_image":
        raise ReferenceReviewError(f"结构复核{review_id}必须依据visible_image")
    row_count = structure_review.get("row_count")
    column_count = structure_review.get("column_count")
    columns = structure_review.get("columns")
    rows = structure_review.get("rows")
    if (
        not isinstance(row_count, int)
        or row_count < 1
        or not isinstance(column_count, int)
        or column_count < 1
        or not isinstance(columns, list)
        or len(columns) != column_count
        or not all(isinstance(column, str) and column for column in columns)
        or not isinstance(rows, list)
        or len(rows) != row_count
    ):
        raise ReferenceReviewError(f"结构复核{review_id}的行列定义不一致")
    row_ids: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ReferenceReviewError(f"结构复核{review_id}的row必须是对象")
        row_id = row.get("row_id")
        cells = row.get("cells")
        if (
            not isinstance(row_id, str)
            or not row_id
            or row_id in row_ids
            or not isinstance(cells, list)
            or len(cells) != column_count
        ):
            raise ReferenceReviewError(f"结构复核{review_id}的row定义无效")
        row_ids.add(row_id)
        column_indices = {cell.get("column_index") for cell in cells}
        if column_indices != set(range(1, column_count + 1)):
            raise ReferenceReviewError(
                f"结构复核{review_id}的列序号必须覆盖1到{column_count}"
            )


def _validate_evaluation_context(evaluation_context: Any) -> None:
    if not isinstance(evaluation_context, dict):
        raise ReferenceReviewError("evaluation_context必须是对象")
    frozen_before_run = evaluation_context.get(
        "reference_frozen_before_model_run"
    )
    usage = evaluation_context.get("usage")
    included = evaluation_context.get("included_in_formal_validation")
    if not isinstance(frozen_before_run, bool) or not isinstance(included, bool):
        raise ReferenceReviewError("evaluation_context的布尔状态无效")
    if usage not in (
        "pre_model_frozen_reference",
        "teaching_post_run_adjudication_only",
    ):
        raise ReferenceReviewError("evaluation_context.usage无效")
    if usage == "teaching_post_run_adjudication_only" and (
        frozen_before_run or included
    ):
        raise ReferenceReviewError(
            "模型运行后裁决的参考结果不得标记为运行前冻结或正式验证"
        )
    if usage == "pre_model_frozen_reference" and not frozen_before_run:
        raise ReferenceReviewError("正式冻结参考必须在模型运行前形成")
    if not isinstance(evaluation_context.get("notes"), str):
        raise ReferenceReviewError("evaluation_context.notes必须是字符串")


def _apply_corrections(
    fields: list[dict[str, Any]], corrections: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[str]]:
    working = deepcopy(fields)
    applied_ids: list[str] = []
    for correction in corrections:
        action = correction["action"]
        correction_id = correction["correction_id"]
        original = correction.get("original")
        corrected = correction.get("corrected")

        if action == "add_field":
            if original is not None or corrected is None:
                raise ReferenceReviewError(
                    f"校正{correction_id}的add_field要求original为null且corrected非空"
                )
            working.append(
                {
                    "key": corrected["key"],
                    "value": corrected["value"],
                    "question_entity_id": correction.get(
                        "source_question_entity_id"
                    ),
                    "answer_entity_id": correction.get(
                        "source_answer_entity_id"
                    ),
                    "reference_origin": "human_correction",
                    "applied_correction_ids": [correction_id],
                }
            )
            applied_ids.append(correction_id)
            continue

        target_index = _find_target_index(working, correction)
        target = working[target_index]
        if original is None or (
            target["key"] != original["key"]
            or target["value"] != original["value"]
        ):
            raise ReferenceReviewError(
                f"校正{correction_id}的original与当前参考字段不一致"
            )

        if action == "remove_field":
            if corrected is not None:
                raise ReferenceReviewError(
                    f"校正{correction_id}的remove_field要求corrected为null"
                )
            del working[target_index]
        else:
            if corrected is None:
                raise ReferenceReviewError(
                    f"校正{correction_id}的{action}要求corrected非空"
                )
            if action == "replace_key" and corrected["value"] != target["value"]:
                raise ReferenceReviewError(
                    f"校正{correction_id}的replace_key不得同时修改值"
                )
            if action == "replace_value" and corrected["key"] != target["key"]:
                raise ReferenceReviewError(
                    f"校正{correction_id}的replace_value不得同时修改键"
                )
            target["key"] = corrected["key"]
            target["value"] = corrected["value"]
            target["reference_origin"] = "human_correction"
            target.setdefault("applied_correction_ids", []).append(correction_id)
        applied_ids.append(correction_id)
    return working, applied_ids


def _apply_structure_reviews(
    fields: list[dict[str, Any]], structure_reviews: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    working = deepcopy(fields)
    assigned_entity_pairs: set[tuple[str, str]] = set()
    for structure_review in structure_reviews:
        review_id = structure_review["review_id"]
        for row in structure_review["rows"]:
            row_id = row["row_id"]
            for cell in row["cells"]:
                question_id = cell["source_question_entity_id"]
                answer_id = cell["source_answer_entity_id"]
                entity_pair = (str(question_id), str(answer_id))
                if entity_pair in assigned_entity_pairs:
                    raise ReferenceReviewError(
                        f"结构复核{review_id}重复引用实体关系{entity_pair}"
                    )
                assigned_entity_pairs.add(entity_pair)
                matches = [
                    field
                    for field in working
                    if str(field.get("question_entity_id"))
                    == str(question_id)
                    and str(field.get("answer_entity_id")) == str(answer_id)
                ]
                if len(matches) != 1:
                    raise ReferenceReviewError(
                        f"结构复核{review_id}无法唯一定位实体关系{entity_pair}"
                    )
                target = matches[0]
                target["structure_group_id"] = review_id
                target["structure_row_id"] = row_id
                target["structure_column_index"] = cell["column_index"]
    return working


def _find_target_index(
    fields: list[dict[str, Any]], correction: dict[str, Any]
) -> int:
    question_id = correction.get("source_question_entity_id")
    answer_id = correction.get("source_answer_entity_id")
    if question_id is None or answer_id is None:
        raise ReferenceReviewError(
            f"校正{correction['correction_id']}缺少原始question-answer实体ID"
        )
    matches = [
        index
        for index, field in enumerate(fields)
        if str(field.get("question_entity_id")) == str(question_id)
        and str(field.get("answer_entity_id")) == str(answer_id)
    ]
    if len(matches) != 1:
        raise ReferenceReviewError(
            f"校正{correction['correction_id']}无法唯一定位原始参考字段"
        )
    return matches[0]
