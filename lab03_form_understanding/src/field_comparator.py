from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any, Iterable

from .text_normalizer import normalize_text


REFERENCE_STATUSES = (
    "exact_match",
    "normalized_match",
    "wrong_value",
    "key_value_mismatch",
    "missing",
    "manual_review",
)


def _normalized_pair(field: dict[str, str]) -> tuple[str, str]:
    return (
        normalize_text(field["key"], is_key=True),
        normalize_text(field["value"]),
    )


def _result_row(
    reference_index: int,
    reference: dict[str, str],
    status: str,
    predicted_index: int | None,
    predicted: dict[str, str] | None,
) -> dict[str, Any]:
    return {
        "reference_index": reference_index,
        "key": reference["key"],
        "value": reference["value"],
        "status": status,
        "predicted_index": predicted_index,
        "predicted_key": predicted["key"] if predicted else None,
        "predicted_value": predicted["value"] if predicted else None,
    }


def _summary(reference_results: list[dict[str, Any]], extra_count: int) -> dict[str, Any]:
    counts = Counter(row["status"] for row in reference_results)
    reference_count = len(reference_results)
    correct = counts["exact_match"] + counts["normalized_match"]
    return {
        "reference_field_count": reference_count,
        "exact_match": counts["exact_match"],
        "normalized_match": counts["normalized_match"],
        "wrong_value": counts["wrong_value"],
        "key_value_mismatch": counts["key_value_mismatch"],
        "missing": counts["missing"],
        "extra": extra_count,
        "manual_review": counts["manual_review"],
        "reference_field_recognition_accuracy": (
            round(correct / reference_count, 4) if reference_count else None
        ),
    }


def compare_fields(
    reference_fields: Iterable[dict[str, str]],
    predicted_fields: Iterable[dict[str, str]],
) -> dict[str, Any]:
    """Compare fields one-to-one without fuzzy matching or silent deduplication."""

    references = [dict(item) for item in reference_fields]
    predictions = [dict(item) for item in predicted_fields]
    results: list[dict[str, Any] | None] = [None] * len(references)
    used_predictions: set[int] = set()

    def assign_pairs(status: str, normalized: bool) -> None:
        for ref_index, reference in enumerate(references):
            if results[ref_index] is not None:
                continue
            reference_pair = _normalized_pair(reference) if normalized else (
                reference["key"],
                reference["value"],
            )
            for pred_index, prediction in enumerate(predictions):
                if pred_index in used_predictions:
                    continue
                predicted_pair = _normalized_pair(prediction) if normalized else (
                    prediction["key"],
                    prediction["value"],
                )
                if reference_pair == predicted_pair:
                    results[ref_index] = _result_row(
                        ref_index, reference, status, pred_index, prediction
                    )
                    used_predictions.add(pred_index)
                    break

    assign_pairs("exact_match", normalized=False)
    assign_pairs("normalized_match", normalized=True)

    unmatched_reference_indices = [
        index for index, result in enumerate(results) if result is None
    ]
    unmatched_value_owners: dict[str, set[str]] = {}
    for index in unmatched_reference_indices:
        key, value = _normalized_pair(references[index])
        unmatched_value_owners.setdefault(value, set()).add(key)

    for ref_index in unmatched_reference_indices:
        if results[ref_index] is not None:
            continue
        reference_key, _ = _normalized_pair(references[ref_index])
        for pred_index, prediction in enumerate(predictions):
            if pred_index in used_predictions:
                continue
            predicted_key, predicted_value = _normalized_pair(prediction)
            value_owner_keys = unmatched_value_owners.get(predicted_value, set())
            if predicted_key == reference_key and any(
                owner_key != reference_key for owner_key in value_owner_keys
            ):
                results[ref_index] = _result_row(
                    ref_index,
                    references[ref_index],
                    "key_value_mismatch",
                    pred_index,
                    prediction,
                )
                used_predictions.add(pred_index)
                break

    for ref_index, reference in enumerate(references):
        if results[ref_index] is not None:
            continue
        reference_key, _ = _normalized_pair(reference)
        for pred_index, prediction in enumerate(predictions):
            if pred_index in used_predictions:
                continue
            predicted_key, _ = _normalized_pair(prediction)
            if reference_key == predicted_key:
                results[ref_index] = _result_row(
                    ref_index, reference, "wrong_value", pred_index, prediction
                )
                used_predictions.add(pred_index)
                break

    for ref_index, reference in enumerate(references):
        if results[ref_index] is None:
            results[ref_index] = _result_row(
                ref_index, reference, "missing", None, None
            )

    final_results = [result for result in results if result is not None]
    extras = [
        {
            "predicted_index": pred_index,
            "key": prediction["key"],
            "value": prediction["value"],
            "status": "extra",
        }
        for pred_index, prediction in enumerate(predictions)
        if pred_index not in used_predictions
    ]
    return {
        "reference_results": final_results,
        "extra_fields": extras,
        "summary": _summary(final_results, len(extras)),
    }


def mark_manual_review(
    comparison: dict[str, Any], reference_index: int, note: str
) -> dict[str, Any]:
    """Return an auditable human-edited copy with one result marked for review."""

    if not note.strip():
        raise ValueError("人工复核必须填写原因")
    updated = deepcopy(comparison)
    rows = updated.get("reference_results", [])
    target = next(
        (row for row in rows if row.get("reference_index") == reference_index), None
    )
    if target is None:
        raise IndexError(f"不存在人工标注参考字段索引：{reference_index}")
    target["status"] = "manual_review"
    target["manual_review_note"] = note.strip()
    updated["summary"] = _summary(rows, len(updated.get("extra_fields", [])))
    return updated
