from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class DataFormatError(ValueError):
    """Raised when an XFUND file does not match the expected structure."""


def load_xfund_documents(annotation_path: Path) -> list[dict[str, Any]]:
    """Load XFUND documents and validate the minimum fields used by this lab."""
    if not annotation_path.is_file():
        raise FileNotFoundError(f"找不到XFUND标注文件：{annotation_path}")

    with annotation_path.open("r", encoding="utf-8") as file:
        payload = json.load(file)

    if not isinstance(payload, dict) or not isinstance(payload.get("documents"), list):
        raise DataFormatError("XFUND标注根对象必须包含documents数组")

    documents: list[dict[str, Any]] = payload["documents"]
    seen_ids: set[str] = set()
    for index, document in enumerate(documents):
        _validate_document(document, index)
        sample_id = str(document["id"])
        if sample_id in seen_ids:
            raise DataFormatError(f"发现重复文档ID：{sample_id}")
        seen_ids.add(sample_id)

    return documents


def _validate_document(document: Any, index: int) -> None:
    if not isinstance(document, dict):
        raise DataFormatError(f"documents[{index}]必须是对象")
    if "id" not in document:
        raise DataFormatError(f"documents[{index}]缺少id")
    if not isinstance(document.get("img"), dict):
        raise DataFormatError(f"documents[{index}]缺少img对象")
    if not isinstance(document["img"].get("fname"), str):
        raise DataFormatError(f"documents[{index}].img缺少fname")
    if not isinstance(document.get("document"), list):
        raise DataFormatError(f"documents[{index}]缺少document数组")

    entity_ids: set[str] = set()
    for entity_index, entity in enumerate(document["document"]):
        if not isinstance(entity, dict):
            raise DataFormatError(
                f"documents[{index}].document[{entity_index}]必须是对象"
            )
        for field in ("id", "text", "label", "linking", "words"):
            if field not in entity:
                raise DataFormatError(
                    f"documents[{index}].document[{entity_index}]缺少{field}"
                )
        entity_id = str(entity["id"])
        if entity_id in entity_ids:
            raise DataFormatError(
                f"文档{document['id']}中发现重复实体ID：{entity_id}"
            )
        entity_ids.add(entity_id)
        if not isinstance(entity["text"], str):
            raise DataFormatError(f"实体{entity_id}的text必须是字符串")
        if not isinstance(entity["label"], str):
            raise DataFormatError(f"实体{entity_id}的label必须是字符串")
        if not isinstance(entity["linking"], list):
            raise DataFormatError(f"实体{entity_id}的linking必须是数组")
        if not isinstance(entity["words"], list):
            raise DataFormatError(f"实体{entity_id}的words必须是数组")


def resolve_image_path(images_dir: Path, document: dict[str, Any]) -> Path:
    """Resolve an image name inside the extracted directory without traversal."""
    relative_name = Path(document["img"]["fname"])
    if relative_name.is_absolute() or ".." in relative_name.parts:
        raise DataFormatError(f"图片文件名包含不安全路径：{relative_name}")

    root = images_dir.resolve()
    image_path = (root / relative_name).resolve()
    try:
        image_path.relative_to(root)
    except ValueError as error:
        raise DataFormatError(f"图片路径越出数据目录：{relative_name}") from error
    return image_path
