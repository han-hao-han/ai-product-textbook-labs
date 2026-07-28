from __future__ import annotations

from collections import Counter
from difflib import SequenceMatcher
import re
from typing import Any, Iterable

from .text_normalizer import normalize_text


DATASET_ANNOTATION_STATUSES = (
    "exact_match",
    "normalized_match",
    "different_value",
    "different_pairing",
    "not_in_model_output",
)

DIAGNOSTIC_HINTS = (
    "reference_value_contained_in_model_value",
    "model_value_contained_in_reference_value",
    "same_value_different_key",
    "checkbox_symbol_difference",
    "same_key_multiple_dataset_values_combined",
    "high_key_similarity",
    "high_value_similarity",
)

_CHECKBOX_SYMBOLS = frozenset(("☑", "□", "☒", "✓", "✔", "√", "■"))
_MERGE_SEPARATORS = re.compile(r"[\s,，、;；|/]+")
_SIMILARITY_THRESHOLD = 0.75


def _normalized_pair(field: dict[str, str]) -> tuple[str, str]:
    return (
        normalize_text(field["key"], is_key=True),
        normalize_text(field["value"]),
    )


def _without_checkbox_symbols(value: str) -> str:
    return normalize_text(
        "".join(character for character in value if character not in _CHECKBOX_SYMBOLS)
    )


def _similarity(left: str, right: str, *, is_key: bool = False) -> float:
    normalized_left = normalize_text(left, is_key=is_key)
    normalized_right = normalize_text(right, is_key=is_key)
    if not normalized_left or not normalized_right:
        return 0.0
    return round(SequenceMatcher(None, normalized_left, normalized_right).ratio(), 4)


def _diagnostic_hints(
    dataset_field: dict[str, str], model_field: dict[str, str]
) -> list[str]:
    dataset_key, dataset_value = _normalized_pair(dataset_field)
    model_key, model_value = _normalized_pair(model_field)
    hints: list[str] = []

    if (
        dataset_value
        and model_value
        and dataset_value != model_value
        and dataset_value in model_value
    ):
        hints.append("reference_value_contained_in_model_value")
    if (
        dataset_value
        and model_value
        and dataset_value != model_value
        and model_value in dataset_value
    ):
        hints.append("model_value_contained_in_reference_value")
    if dataset_value == model_value and dataset_key != model_key:
        hints.append("same_value_different_key")

    dataset_symbols = [
        char for char in dataset_value if char in _CHECKBOX_SYMBOLS
    ]
    model_symbols = [char for char in model_value if char in _CHECKBOX_SYMBOLS]
    if (
        dataset_symbols != model_symbols
        and (dataset_symbols or model_symbols)
        and _without_checkbox_symbols(dataset_value)
        == _without_checkbox_symbols(model_value)
    ):
        hints.append("checkbox_symbol_difference")
    key_similarity = _similarity(
        dataset_field["key"], model_field["key"], is_key=True
    )
    value_similarity = _similarity(dataset_field["value"], model_field["value"])
    if (
        dataset_key != model_key
        and max(len(dataset_key), len(model_key)) >= 4
        and key_similarity >= _SIMILARITY_THRESHOLD
    ):
        hints.append("high_key_similarity")
    if (
        dataset_value != model_value
        and max(len(dataset_value), len(model_value)) >= 4
        and value_similarity >= _SIMILARITY_THRESHOLD
    ):
        hints.append("high_value_similarity")
    return hints


def _diagnostic_scores(
    dataset_field: dict[str, str], model_field: dict[str, str]
) -> dict[str, float]:
    return {
        "key_similarity": _similarity(
            dataset_field["key"], model_field["key"], is_key=True
        ),
        "value_similarity": _similarity(
            dataset_field["value"], model_field["value"]
        ),
    }


def _pair_diagnostic_links(
    dataset_items: list[dict[str, str]], model_items: list[dict[str, str]]
) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    for dataset_index, dataset_field in enumerate(dataset_items):
        for model_index, model_field in enumerate(model_items):
            hints = _diagnostic_hints(dataset_field, model_field)
            if not hints:
                continue
            links.append(
                {
                    "dataset_annotation_indices": [dataset_index],
                    "model_indices": [model_index],
                    "diagnostic_hints": hints,
                    "similarity_scores": _diagnostic_scores(
                        dataset_field, model_field
                    ),
                }
            )
    return links


def _multiline_merge_diagnostic_links(
    dataset_items: list[dict[str, str]], model_items: list[dict[str, str]]
) -> list[dict[str, Any]]:
    dataset_groups: dict[str, list[int]] = {}
    for dataset_index, dataset_field in enumerate(dataset_items):
        normalized_key, _ = _normalized_pair(dataset_field)
        dataset_groups.setdefault(normalized_key, []).append(dataset_index)

    links: list[dict[str, Any]] = []
    for normalized_key, dataset_indices in dataset_groups.items():
        if len(dataset_indices) < 2:
            continue
        dataset_values = [
            _MERGE_SEPARATORS.sub(
                "", normalize_text(dataset_items[index]["value"])
            )
            for index in dataset_indices
        ]
        if any(not value for value in dataset_values):
            continue
        combined_dataset_value = "".join(dataset_values)
        for model_index, model_field in enumerate(model_items):
            model_key, model_value = _normalized_pair(model_field)
            compact_model_value = _MERGE_SEPARATORS.sub("", model_value)
            if (
                model_key == normalized_key
                and compact_model_value == combined_dataset_value
            ):
                links.append(
                    {
                        "dataset_annotation_indices": dataset_indices,
                        "model_indices": [model_index],
                        "diagnostic_hints": [
                            "same_key_multiple_dataset_values_combined"
                        ],
                        "similarity_scores": {
                            "key_similarity": 1.0,
                            "value_similarity": 1.0,
                        },
                    }
                )
    return links


def _dataset_row(
    dataset_index: int,
    dataset_field: dict[str, str],
    status: str,
    model_index: int | None,
    model_field: dict[str, str] | None,
) -> dict[str, Any]:
    return {
        "dataset_annotation_index": dataset_index,
        "dataset_key": dataset_field["key"],
        "dataset_value": dataset_field["value"],
        "status": status,
        "model_index": model_index,
        "model_key": model_field["key"] if model_field else None,
        "model_value": model_field["value"] if model_field else None,
        "diagnostic_hints": (
            _diagnostic_hints(dataset_field, model_field) if model_field else []
        ),
    }


def _summary(
    dataset_rows: list[dict[str, Any]], model_only_count: int
) -> dict[str, Any]:
    counts = Counter(row["status"] for row in dataset_rows)
    dataset_count = len(dataset_rows)
    consistent = counts["exact_match"] + counts["normalized_match"]
    return {
        "dataset_annotation_field_count": dataset_count,
        "exact_match": counts["exact_match"],
        "normalized_match": counts["normalized_match"],
        "different_value": counts["different_value"],
        "different_pairing": counts["different_pairing"],
        "not_in_model_output": counts["not_in_model_output"],
        "not_in_dataset_annotation": model_only_count,
        "dataset_annotation_consistency_rate": (
            round(consistent / dataset_count, 4) if dataset_count else None
        ),
    }


def compare_dataset_annotation(
    dataset_fields: Iterable[dict[str, str]],
    model_fields: Iterable[dict[str, str]],
) -> dict[str, Any]:
    """Compare model output with dataset annotations without judging correctness.

    Matching is deterministic and one-to-one. Diagnostic hints only help a human
    locate likely causes of disagreement; they never change a status to a match.
    """

    dataset_items = [dict(item) for item in dataset_fields]
    model_items = [dict(item) for item in model_fields]
    rows: list[dict[str, Any] | None] = [None] * len(dataset_items)
    used_model_indices: set[int] = set()

    def assign_pairs(status: str, *, normalized: bool) -> None:
        for dataset_index, dataset_field in enumerate(dataset_items):
            if rows[dataset_index] is not None:
                continue
            dataset_pair = (
                _normalized_pair(dataset_field)
                if normalized
                else (dataset_field["key"], dataset_field["value"])
            )
            for model_index, model_field in enumerate(model_items):
                if model_index in used_model_indices:
                    continue
                model_pair = (
                    _normalized_pair(model_field)
                    if normalized
                    else (model_field["key"], model_field["value"])
                )
                if dataset_pair == model_pair:
                    rows[dataset_index] = _dataset_row(
                        dataset_index,
                        dataset_field,
                        status,
                        model_index,
                        model_field,
                    )
                    used_model_indices.add(model_index)
                    break

    assign_pairs("exact_match", normalized=False)
    assign_pairs("normalized_match", normalized=True)

    unmatched_dataset_indices = [
        index for index, result in enumerate(rows) if result is None
    ]
    unmatched_value_owners: dict[str, set[str]] = {}
    for index in unmatched_dataset_indices:
        key, value = _normalized_pair(dataset_items[index])
        unmatched_value_owners.setdefault(value, set()).add(key)

    for dataset_index in unmatched_dataset_indices:
        if rows[dataset_index] is not None:
            continue
        dataset_key, _ = _normalized_pair(dataset_items[dataset_index])
        for model_index, model_field in enumerate(model_items):
            if model_index in used_model_indices:
                continue
            model_key, model_value = _normalized_pair(model_field)
            value_owner_keys = unmatched_value_owners.get(model_value, set())
            if model_key == dataset_key and any(
                owner_key != dataset_key for owner_key in value_owner_keys
            ):
                rows[dataset_index] = _dataset_row(
                    dataset_index,
                    dataset_items[dataset_index],
                    "different_pairing",
                    model_index,
                    model_field,
                )
                used_model_indices.add(model_index)
                break

    for dataset_index, dataset_field in enumerate(dataset_items):
        if rows[dataset_index] is not None:
            continue
        dataset_key, _ = _normalized_pair(dataset_field)
        for model_index, model_field in enumerate(model_items):
            if model_index in used_model_indices:
                continue
            model_key, _ = _normalized_pair(model_field)
            if dataset_key == model_key:
                rows[dataset_index] = _dataset_row(
                    dataset_index,
                    dataset_field,
                    "different_value",
                    model_index,
                    model_field,
                )
                used_model_indices.add(model_index)
                break

    for dataset_index, dataset_field in enumerate(dataset_items):
        if rows[dataset_index] is None:
            rows[dataset_index] = _dataset_row(
                dataset_index,
                dataset_field,
                "not_in_model_output",
                None,
                None,
            )

    final_rows = [row for row in rows if row is not None]
    model_only_fields = []
    for model_index, model_field in enumerate(model_items):
        if model_index in used_model_indices:
            continue
        diagnostic_hints: list[str] = []
        for dataset_field in dataset_items:
            for hint in _diagnostic_hints(dataset_field, model_field):
                if hint not in diagnostic_hints:
                    diagnostic_hints.append(hint)
        model_only_fields.append(
            {
                "model_index": model_index,
                "model_key": model_field["key"],
                "model_value": model_field["value"],
                "status": "not_in_dataset_annotation",
                "diagnostic_hints": diagnostic_hints,
            }
        )

    return {
        "dataset_annotation_results": final_rows,
        "model_only_fields": model_only_fields,
        "diagnostic_links": (
            _pair_diagnostic_links(dataset_items, model_items)
            + _multiline_merge_diagnostic_links(dataset_items, model_items)
        ),
        "summary": _summary(final_rows, len(model_only_fields)),
        "interpretation": {
            "metric": "dataset_annotation_consistency_rate",
            "is_accuracy_metric": False,
            "diagnostic_hints_are_judgments": False,
            "similarity_threshold": _SIMILARITY_THRESHOLD,
        },
    }
