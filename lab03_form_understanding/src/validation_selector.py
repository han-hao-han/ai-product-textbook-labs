from __future__ import annotations

from collections import Counter
from typing import Any

from src.candidate_selector import (
    count_entity_labels,
    extract_annotation_features,
)
from src.privacy_screening import screen_document_privacy
from src.reference_converter import convert_reference_fields
from src.xfund_loader import resolve_image_path


class ValidationSelectionError(RuntimeError):
    """Raised when 12 transparent validation candidates cannot be generated."""


DIFFICULTY_GROUPS = ("simple", "medium", "complex")
DIFFICULTY_LABELS = {
    "simple": "简单",
    "medium": "中等",
    "complex": "较复杂",
}
FEATURE_WEIGHTS = {
    "reference_field_count": 0.30,
    "entity_count": 0.20,
    "longest_value_chars": 0.15,
    "multiline_entity_count": 0.15,
    "mean_pair_distance": 0.15,
    "duplicate_key_count": 0.05,
}


def select_validation_candidates(
    documents: list[dict[str, Any]],
    images_dir,
    *,
    excluded_ids: set[str],
) -> list[dict[str, Any]]:
    """Build 4 candidates per difficulty group from annotation-only features."""
    eligible: list[dict[str, Any]] = []
    for document in documents:
        sample_id = str(document["id"])
        if sample_id in excluded_ids:
            continue
        image_path = resolve_image_path(images_dir, document)
        reference = convert_reference_fields(document)
        privacy_screen = screen_document_privacy(document)
        if not image_path.is_file():
            continue
        if len(reference["reference_fields"]) < 2:
            continue
        if reference["conversion_warnings"]:
            continue
        if privacy_screen["hard_excluded"]:
            continue

        features = extract_annotation_features(document, reference)
        key_counts = Counter(field["key"] for field in reference["reference_fields"])
        features["duplicate_key_count"] = sum(
            count - 1 for count in key_counts.values() if count > 1
        )
        eligible.append(
            {
                "sample_id": sample_id,
                "image_path": image_path,
                "label_counts": count_entity_labels(document),
                "reference": reference,
                "features": features,
                "privacy_screen": privacy_screen,
            }
        )

    if len(eligible) < 12:
        raise ValidationSelectionError(
            f"排除固定样本后只有{len(eligible)}张合格数据，无法生成12张候选"
        )

    _attach_difficulty_scores(eligible)
    ranked = sorted(eligible, key=lambda item: (item["difficulty_score"], item["sample_id"]))
    pools = _split_into_three_pools(ranked)

    selected: list[dict[str, Any]] = []
    for group in DIFFICULTY_GROUPS:
        group_candidates = _pick_evenly(pools[group], count=4)
        for order, item in enumerate(group_candidates, start=1):
            selected_item = dict(item)
            selected_item["difficulty_group"] = group
            selected_item["difficulty_label"] = DIFFICULTY_LABELS[group]
            selected_item["candidate_order_in_group"] = order
            selected.append(selected_item)

    selected_ids = {item["sample_id"] for item in selected}
    if len(selected_ids) != 12:
        raise ValidationSelectionError("验证候选存在重复")
    if selected_ids & excluded_ids:
        raise ValidationSelectionError("验证候选与主样本或观察样本重叠")
    return selected


def _attach_difficulty_scores(items: list[dict[str, Any]]) -> None:
    bounds: dict[str, tuple[float, float]] = {}
    for feature in FEATURE_WEIGHTS:
        values = [float(item["features"][feature]) for item in items]
        bounds[feature] = min(values), max(values)

    for item in items:
        normalized: dict[str, float] = {}
        contributions: dict[str, float] = {}
        for feature, weight in FEATURE_WEIGHTS.items():
            minimum, maximum = bounds[feature]
            value = float(item["features"][feature])
            normalized_value = 0.0 if maximum == minimum else (value - minimum) / (maximum - minimum)
            normalized[feature] = round(normalized_value, 4)
            contributions[feature] = round(normalized_value * weight * 100, 2)
        item["difficulty_score"] = round(sum(contributions.values()), 2)
        item["difficulty_details"] = {
            "feature_weights": FEATURE_WEIGHTS,
            "normalized_features": normalized,
            "score_contributions": contributions,
        }


def _split_into_three_pools(
    ranked: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    first_boundary = len(ranked) // 3
    second_boundary = len(ranked) * 2 // 3
    pools = {
        "simple": ranked[:first_boundary],
        "medium": ranked[first_boundary:second_boundary],
        "complex": ranked[second_boundary:],
    }
    if any(len(pool) < 4 for pool in pools.values()):
        raise ValidationSelectionError("难度分组中不足4张候选")
    return pools


def _pick_evenly(items: list[dict[str, Any]], *, count: int) -> list[dict[str, Any]]:
    if len(items) < count:
        raise ValidationSelectionError("候选池不足")
    if count == 1:
        return [items[len(items) // 2]]
    indices = [round(index * (len(items) - 1) / (count - 1)) for index in range(count)]
    return [items[index] for index in indices]
