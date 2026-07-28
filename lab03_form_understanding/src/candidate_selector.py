from __future__ import annotations

import math
import statistics
from typing import Any

from src.privacy_screening import screen_document_privacy
from src.reference_converter import convert_reference_fields
from src.xfund_loader import resolve_image_path


class CandidateSelectionError(RuntimeError):
    """Raised when five valid real-data candidates cannot be prepared."""


ROLE_LABELS = (
    "字段数量适中",
    "字段较多",
    "键值距离较远",
    "长值或多行文本",
    "布局较复杂",
)


def select_candidates(
    documents: list[dict[str, Any]],
    images_dir,
    *,
    candidate_count: int = 5,
) -> list[dict[str, Any]]:
    """Select deterministic candidates from annotation features, never model results."""
    if candidate_count != 5:
        raise CandidateSelectionError("任务契约要求固定生成5张真实候选")

    candidates = build_candidate_pool(documents, images_dir)

    if len(candidates) < candidate_count:
        raise CandidateSelectionError(
            f"只有{len(candidates)}张样本满足候选条件，少于任务契约要求的5张"
        )

    median_fields = statistics.median(
        candidate["features"]["reference_field_count"] for candidate in candidates
    )
    rankings = {
        "字段数量适中": sorted(
            candidates,
            key=lambda item: (
                abs(item["features"]["reference_field_count"] - median_fields),
                item["features"]["reference_field_count"],
                item["sample_id"],
            ),
        ),
        "字段较多": _rank_desc(candidates, "reference_field_count"),
        "键值距离较远": _rank_desc(candidates, "mean_pair_distance"),
        "长值或多行文本": sorted(
            candidates,
            key=lambda item: (
                -item["features"]["longest_value_chars"],
                -item["features"]["multiline_entity_count"],
                item["sample_id"],
            ),
        ),
        "布局较复杂": _rank_desc(candidates, "layout_complexity"),
    }

    selected: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    for role in ROLE_LABELS:
        candidate = next(
            (item for item in rankings[role] if item["sample_id"] not in used_ids),
            None,
        )
        if candidate is None:
            raise CandidateSelectionError(f"无法为候选角色“{role}”找到独立样本")
        selected_item = dict(candidate)
        selected_item["candidate_role"] = role
        selected_item["selection_reason"] = _selection_reason(
            role,
            candidate["features"],
        )
        selected.append(selected_item)
        used_ids.add(candidate["sample_id"])

    return selected


def build_candidate_pool(
    documents: list[dict[str, Any]],
    images_dir,
) -> list[dict[str, Any]]:
    """Build the eligible pool without retaining matched privacy literals."""
    candidates: list[dict[str, Any]] = []
    for document in documents:
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
        candidates.append(
            {
                "sample_id": str(document["id"]),
                "image_path": image_path,
                "label_counts": count_entity_labels(document),
                "reference": reference,
                "features": extract_annotation_features(document, reference),
                "privacy_screen": privacy_screen,
            }
        )
    return candidates


def _rank_desc(candidates: list[dict[str, Any]], feature: str) -> list[dict[str, Any]]:
    return sorted(
        candidates,
        key=lambda item: (
            -item["features"][feature],
            item["sample_id"],
        ),
    )


def count_entity_labels(document: dict[str, Any]) -> dict[str, int]:
    counts = {"header": 0, "question": 0, "answer": 0, "other": 0}
    for entity in document["document"]:
        label = entity["label"].lower()
        counts[label] = counts.get(label, 0) + 1
    return counts


def extract_annotation_features(
    document: dict[str, Any], reference: dict[str, Any]
) -> dict[str, Any]:
    fields = reference["reference_fields"]
    entities = document["document"]
    id_to_entity = {str(entity["id"]): entity for entity in entities}
    distances: list[float] = []
    for field in fields:
        question = id_to_entity[str(field["question_entity_id"])]
        answer = id_to_entity[str(field["answer_entity_id"])]
        distance = _normalized_center_distance(document, question, answer)
        if distance is not None:
            distances.append(distance)

    multiline_count = sum(_is_multiline(entity) for entity in entities)
    longest_value = max((len(field["value"]) for field in fields), default=0)
    layout_complexity = len(entities) + 3 * multiline_count + len(fields)
    return {
        "reference_field_count": len(fields),
        "entity_count": len(entities),
        "longest_value_chars": longest_value,
        "multiline_entity_count": multiline_count,
        "mean_pair_distance": round(statistics.mean(distances), 4) if distances else 0.0,
        "layout_complexity": layout_complexity,
    }


def _normalized_center_distance(
    document: dict[str, Any],
    left: dict[str, Any],
    right: dict[str, Any],
) -> float | None:
    left_box = _entity_box(left)
    right_box = _entity_box(right)
    if left_box is None or right_box is None:
        return None
    width, height = _document_size(document)
    diagonal = math.hypot(width, height)
    if diagonal <= 0:
        return None
    left_center = ((left_box[0] + left_box[2]) / 2, (left_box[1] + left_box[3]) / 2)
    right_center = ((right_box[0] + right_box[2]) / 2, (right_box[1] + right_box[3]) / 2)
    return math.dist(left_center, right_center) / diagonal


def _document_size(document: dict[str, Any]) -> tuple[float, float]:
    img = document.get("img", {})
    width = _positive_number(img.get("width"))
    height = _positive_number(img.get("height"))
    if width and height:
        return width, height

    boxes = [
        box
        for entity in document["document"]
        for word in entity["words"]
        if (box := _valid_box(word.get("box"))) is not None
    ]
    if not boxes:
        return 1.0, 1.0
    return max(box[2] for box in boxes) or 1.0, max(box[3] for box in boxes) or 1.0


def _positive_number(value: Any) -> float | None:
    if isinstance(value, (int, float)) and value > 0:
        return float(value)
    return None


def _entity_box(entity: dict[str, Any]) -> tuple[float, float, float, float] | None:
    boxes = [
        box
        for word in entity["words"]
        if (box := _valid_box(word.get("box"))) is not None
    ]
    if not boxes:
        return None
    return (
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    )


def _valid_box(value: Any) -> tuple[float, float, float, float] | None:
    if not isinstance(value, list) or len(value) != 4:
        return None
    if not all(isinstance(number, (int, float)) for number in value):
        return None
    return tuple(float(number) for number in value)


def _is_multiline(entity: dict[str, Any]) -> int:
    boxes = [
        box
        for word in entity["words"]
        if (box := _valid_box(word.get("box"))) is not None
    ]
    if len(boxes) < 2:
        return 0
    centers = [(box[1] + box[3]) / 2 for box in boxes]
    heights = [max(1.0, box[3] - box[1]) for box in boxes]
    return int(max(centers) - min(centers) > statistics.median(heights))


def _selection_reason(
    role: str,
    features: dict[str, Any],
) -> str:
    if role == "字段数量适中":
        return f"显式参考字段为{features['reference_field_count']}组"
    if role == "字段较多":
        return f"显式参考字段较多，共{features['reference_field_count']}组"
    if role == "键值距离较远":
        return f"键值平均归一化距离为{features['mean_pair_distance']}"
    if role == "长值或多行文本":
        return (
            f"最长值为{features['longest_value_chars']}个字符，"
            f"多行实体{features['multiline_entity_count']}个"
        )
    return f"布局复杂度特征值为{features['layout_complexity']}"
