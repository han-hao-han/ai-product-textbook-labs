from __future__ import annotations

from typing import Any


def convert_reference_fields(document: dict[str, Any]) -> dict[str, Any]:
    """Convert only explicit question-answer links into reference fields."""
    entities = document["document"]
    id_to_entity = {str(entity["id"]): entity for entity in entities}
    warnings: list[str] = []
    relations: set[tuple[str, str]] = set()

    for entity in entities:
        for raw_link in entity["linking"]:
            if not isinstance(raw_link, list) or len(raw_link) != 2:
                warnings.append(
                    f"实体{entity['id']}包含格式无效的linking：{raw_link!r}"
                )
                continue
            left_id, right_id = str(raw_link[0]), str(raw_link[1])
            relations.add(tuple(sorted((left_id, right_id))))

    reference_fields: list[dict[str, Any]] = []
    for left_id, right_id in sorted(relations, key=_relation_sort_key):
        left = id_to_entity.get(left_id)
        right = id_to_entity.get(right_id)
        if left is None or right is None:
            warnings.append(f"关系{left_id}-{right_id}指向不存在的实体")
            continue

        pair = {left["label"].lower(), right["label"].lower()}
        if pair != {"question", "answer"}:
            continue

        question = left if left["label"].lower() == "question" else right
        answer = right if question is left else left
        key = question["text"].strip()
        value = answer["text"].strip()
        if not key or not value:
            warnings.append(
                f"关系{question['id']}-{answer['id']}包含空的question或answer文本"
            )
            continue

        reference_fields.append(
            {
                "key": key,
                "value": value,
                "question_entity_id": question["id"],
                "answer_entity_id": answer["id"],
            }
        )

    return {
        "sample_id": str(document["id"]),
        "image_file": document["img"]["fname"],
        "reference_fields": reference_fields,
        "conversion_warnings": warnings,
    }


def _relation_sort_key(relation: tuple[str, str]) -> tuple[tuple[int, str], tuple[int, str]]:
    return _id_sort_key(relation[0]), _id_sort_key(relation[1])


def _id_sort_key(value: str) -> tuple[int, str]:
    try:
        return 0, f"{int(value):020d}"
    except ValueError:
        return 1, value
