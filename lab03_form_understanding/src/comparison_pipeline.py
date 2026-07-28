from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .dataset_annotation_comparator import compare_dataset_annotation
from .field_comparator import compare_fields
from .reference_converter import convert_reference_fields
from .reference_review import (
    build_final_reference,
    load_sample_review_record,
)
from .result_store import portable_path, write_json_atomic
from .schemas import FormExtractionResult


COMPARISON_VERSION = "v2"


class ComparisonInputError(ValueError):
    """A saved model result cannot be used for deterministic comparison."""


def load_saved_model_result(
    result_path: Path, *, expected_sample_id: str
) -> tuple[dict[str, Any], FormExtractionResult]:
    if not result_path.is_file():
        raise FileNotFoundError(
            f"找不到模型结果：{result_path}；请先运行scripts/step02_extract_form.py"
        )
    try:
        with result_path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except json.JSONDecodeError as error:
        raise ComparisonInputError("模型结果文件不是合法JSON") from error

    if not isinstance(payload, dict):
        raise ComparisonInputError("模型结果顶层必须是对象")
    metadata = payload.get("metadata")
    result = payload.get("result")
    if not isinstance(metadata, dict) or not isinstance(result, dict):
        raise ComparisonInputError("模型结果必须包含metadata和result对象")
    if metadata.get("sample_id") != expected_sample_id:
        raise ComparisonInputError(
            f"结果样本ID为{metadata.get('sample_id')}，与请求的{expected_sample_id}不一致"
        )
    if not isinstance(metadata.get("run_id"), str) or not metadata["run_id"]:
        raise ComparisonInputError("模型结果缺少run_id")
    try:
        validated = FormExtractionResult.model_validate(result)
    except ValidationError as error:
        raise ComparisonInputError("模型结果未通过Schema v1校验") from error
    return payload, validated


def compare_saved_result(
    *,
    sample_id: str,
    result_path: Path,
    document: dict[str, Any],
    comparisons_dir: Path,
    project_root: Path,
    review_records_dir: Path | None = None,
) -> dict[str, Any]:
    if str(document.get("id")) != sample_id:
        raise ComparisonInputError("人工标注参考文档与请求样本ID不一致")

    saved_payload, predicted = load_saved_model_result(
        result_path, expected_sample_id=sample_id
    )
    dataset_annotation = convert_reference_fields(document)
    dataset_fields = dataset_annotation["reference_fields"]
    model_fields = [field.model_dump(mode="json") for field in predicted.fields]
    dataset_comparison = compare_dataset_annotation(
        ({"key": item["key"], "value": item["value"]} for item in dataset_fields),
        model_fields,
    )
    for row in dataset_comparison["dataset_annotation_results"]:
        source = dataset_fields[row["dataset_annotation_index"]]
        row["question_entity_id"] = source["question_entity_id"]
        row["answer_entity_id"] = source["answer_entity_id"]

    review_record = None
    review_record_file = None
    if review_records_dir is not None:
        review_record = load_sample_review_record(review_records_dir, sample_id)
        review_record_file = portable_path(
            review_records_dir / f"{sample_id}.json", project_root
        )
    final_reference = build_final_reference(dataset_fields, review_record)
    final_comparison = None
    final_fields = final_reference["final_reference_fields"]
    if final_reference["available_for_accuracy"] and final_fields is not None:
        final_comparison = compare_fields(
            ({"key": item["key"], "value": item["value"]} for item in final_fields),
            model_fields,
        )
        for row in final_comparison["reference_results"]:
            source = final_fields[row["reference_index"]]
            row["question_entity_id"] = source.get("question_entity_id")
            row["answer_entity_id"] = source.get("answer_entity_id")
            row["reference_origin"] = source.get(
                "reference_origin", "dataset_annotation"
            )
            row["applied_correction_ids"] = source.get(
                "applied_correction_ids", []
            )
            row["structure_group_id"] = source.get("structure_group_id")
            row["structure_row_id"] = source.get("structure_row_id")
            row["structure_column_index"] = source.get(
                "structure_column_index"
            )

    compared_at = datetime.now(timezone.utc)
    comparison_run_id = compared_at.strftime("%Y%m%dT%H%M%S_%fZ")
    model_metadata = saved_payload["metadata"]
    output_path = comparisons_dir / (
        f"{sample_id}_{model_metadata['run_id']}_{comparison_run_id}.json"
    )
    output = {
        "metadata": {
            "sample_id": sample_id,
            "comparison_run_id": comparison_run_id,
            "compared_at": compared_at.isoformat(),
            "comparison_version": COMPARISON_VERSION,
            "source_result_file": portable_path(result_path, project_root),
            "model_run_id": model_metadata["run_id"],
            "model": model_metadata.get("model"),
            "prompt_version": model_metadata.get("prompt_version"),
            "schema_version": model_metadata.get("schema_version"),
        },
        "dataset_annotation": {
            "source": "XFUND v1.0 explicit question-answer relations",
            "field_count": len(dataset_fields),
            "conversion_warnings": dataset_annotation["conversion_warnings"],
            "is_assumed_correct": False,
        },
        "dataset_annotation_comparison": dataset_comparison,
        "final_reference": {
            "status": final_reference["status"],
            "available_for_accuracy": final_reference[
                "available_for_accuracy"
            ],
            "reason": final_reference["reason"],
            "review_record_file": review_record_file,
            "field_count": len(final_fields) if final_fields is not None else None,
            "applied_correction_ids": final_reference[
                "applied_correction_ids"
            ],
            "recorded_correction_ids": final_reference.get(
                "recorded_correction_ids", []
            ),
            "correction_preview_field_count": final_reference.get(
                "correction_preview_field_count"
            ),
            "evaluation_context": final_reference.get(
                "evaluation_context"
            ),
        },
        "final_reference_comparison": final_comparison,
    }
    write_json_atomic(output_path, output)
    return {"output_path": output_path, "payload": output}
