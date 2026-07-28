from __future__ import annotations

from pathlib import Path
from typing import Any

from .comparison_pipeline import compare_saved_result
from .extraction_pipeline import run_extraction
from .reference_converter import convert_reference_fields
from .result_store import portable_path
from .xfund_loader import resolve_image_path


class SampleServiceError(ValueError):
    """A requested built-in sample is not present in the loaded XFUND split."""


def find_document(documents: list[dict[str, Any]], sample_id: str) -> dict[str, Any]:
    document = next(
        (item for item in documents if str(item.get("id")) == sample_id), None
    )
    if document is None:
        raise SampleServiceError(f"XFUND标注中不存在样本：{sample_id}")
    return document


def run_builtin_sample(
    *,
    sample_id: str,
    document: dict[str, Any],
    images_dir: Path,
    client: Any,
    results_dir: Path,
    project_root: Path,
    secrets: tuple[str, ...] = (),
    include_final_reference: bool = True,
) -> dict[str, Any]:
    image_path = resolve_image_path(images_dir, document)
    if not image_path.is_file():
        raise FileNotFoundError(f"找不到样本图片：{image_path}")
    extraction = run_extraction(
        sample_id=sample_id,
        image_path=image_path,
        client=client,
        results_dir=results_dir,
        update_current=True,
        secrets=secrets,
    )
    comparison = compare_saved_result(
        sample_id=sample_id,
        result_path=extraction["parsed_path"],
        document=document,
        comparisons_dir=results_dir / "comparisons",
        project_root=project_root,
        review_records_dir=(
            project_root / "data" / "local" / "sample_reviews"
            if include_final_reference
            else None
        ),
    )
    reference = convert_reference_fields(document)
    return {
        "input_type": "builtin",
        "sample_id": sample_id,
        "image_path": portable_path(image_path, project_root),
        "model": extraction["model"],
        "model_run_id": extraction["run_id"],
        "finish_reason": extraction["finish_reason"],
        "elapsed_seconds": extraction["elapsed_seconds"],
        "usage": extraction["usage"],
        "raw_response": extraction["response_text"],
        "result": extraction["parsed"].model_dump(mode="json"),
        "reference": reference,
        "comparison": comparison["payload"],
        "files": {
            "raw": portable_path(extraction["raw_path"], project_root),
            "parsed": portable_path(extraction["parsed_path"], project_root),
            "current": portable_path(extraction["current_path"], project_root),
            "comparison": portable_path(comparison["output_path"], project_root),
        },
    }


def run_custom_sample(
    *,
    sample_id: str,
    image_path: Path,
    client: Any,
    results_dir: Path,
    project_root: Path,
    secrets: tuple[str, ...] = (),
) -> dict[str, Any]:
    extraction = run_extraction(
        sample_id=sample_id,
        image_path=image_path,
        client=client,
        results_dir=results_dir,
        update_current=True,
        secrets=secrets,
    )
    return {
        "input_type": "custom",
        "sample_id": sample_id,
        "image_path": portable_path(image_path, project_root),
        "model": extraction["model"],
        "model_run_id": extraction["run_id"],
        "finish_reason": extraction["finish_reason"],
        "elapsed_seconds": extraction["elapsed_seconds"],
        "usage": extraction["usage"],
        "raw_response": extraction["response_text"],
        "result": extraction["parsed"].model_dump(mode="json"),
        "reference": None,
        "comparison": None,
        "notice": "当前输入没有人工标注参考结果，系统只能检查输出结构，不能自动判断内容是否正确。",
        "files": {
            "raw": portable_path(extraction["raw_path"], project_root),
            "parsed": portable_path(extraction["parsed_path"], project_root),
            "current": portable_path(extraction["current_path"], project_root),
        },
    }
