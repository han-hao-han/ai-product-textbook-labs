from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .result_store import portable_path, safe_error_message, write_json_atomic
from .sample_service import find_document, run_builtin_sample


ProgressCallback = Callable[[int, int, str, str], None]
DATASET_SUMMARY_KEYS = (
    "dataset_annotation_field_count",
    "exact_match",
    "normalized_match",
    "different_value",
    "different_pairing",
    "not_in_model_output",
    "not_in_dataset_annotation",
)


def _empty_counts(keys: tuple[str, ...]) -> dict[str, int]:
    return {key: 0 for key in keys}


def _add_counts(
    target: dict[str, int], summary: dict[str, Any], keys: tuple[str, ...]
) -> None:
    for key in keys:
        target[key] += int(summary[key])


def _with_dataset_consistency(counts: dict[str, int]) -> dict[str, Any]:
    result: dict[str, Any] = dict(counts)
    denominator = counts["dataset_annotation_field_count"]
    consistent = counts["exact_match"] + counts["normalized_match"]
    result["dataset_annotation_consistency_rate"] = (
        round(consistent / denominator, 4) if denominator else None
    )
    return result


def run_fixed_validation(
    *,
    validation_samples: list[dict[str, Any]],
    documents: list[dict[str, Any]],
    images_dir: Path,
    client: Any,
    results_dir: Path,
    project_root: Path,
    secrets: tuple[str, ...] = (),
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    if len(validation_samples) != 6:
        raise ValueError("正式固定验证必须包含6张冻结样本")
    ordered = sorted(validation_samples, key=lambda item: item["validation_order"])
    if [item["validation_order"] for item in ordered] != [1, 2, 3, 4, 5, 6]:
        raise ValueError("固定验证顺序必须为1到6")

    started_at = datetime.now(timezone.utc)
    validation_run_id = started_at.strftime("%Y%m%dT%H%M%S_%fZ")
    sample_results: list[dict[str, Any]] = []
    overall_dataset_counts = _empty_counts(DATASET_SUMMARY_KEYS)
    difficulty_dataset_counts: dict[str, dict[str, int]] = defaultdict(
        lambda: _empty_counts(DATASET_SUMMARY_KEYS)
    )
    difficulty_success: dict[str, int] = defaultdict(int)
    difficulty_failure: dict[str, int] = defaultdict(int)
    difficulty_fields: dict[str, int] = defaultdict(int)
    difficulty_warnings: dict[str, int] = defaultdict(int)
    difficulty_elapsed: dict[str, float] = defaultdict(float)
    total_fields = 0
    total_warnings = 0
    total_elapsed = 0.0
    total = len(ordered)

    for index, sample in enumerate(ordered, start=1):
        sample_id = sample["sample_id"]
        difficulty = sample["difficulty_group"]
        if progress_callback:
            progress_callback(index, total, sample_id, "running")
        try:
            document = find_document(documents, sample_id)
            outcome = run_builtin_sample(
                sample_id=sample_id,
                document=document,
                images_dir=images_dir,
                client=client,
                results_dir=results_dir,
                project_root=project_root,
                secrets=secrets,
                include_final_reference=False,
            )
            dataset_summary = outcome["comparison"][
                "dataset_annotation_comparison"
            ]["summary"]
            field_count = len(outcome["result"]["fields"])
            warning_count = len(outcome["result"]["warnings"])
            elapsed_seconds = float(outcome["elapsed_seconds"])
            _add_counts(
                overall_dataset_counts,
                dataset_summary,
                DATASET_SUMMARY_KEYS,
            )
            _add_counts(
                difficulty_dataset_counts[difficulty],
                dataset_summary,
                DATASET_SUMMARY_KEYS,
            )
            total_fields += field_count
            total_warnings += warning_count
            total_elapsed += elapsed_seconds
            difficulty_fields[difficulty] += field_count
            difficulty_warnings[difficulty] += warning_count
            difficulty_elapsed[difficulty] += elapsed_seconds
            difficulty_success[difficulty] += 1
            sample_results.append(
                {
                    "sample_id": sample_id,
                    "validation_order": sample["validation_order"],
                    "difficulty_group": difficulty,
                    "status": "success",
                    "model_run_id": outcome["model_run_id"],
                    "field_count": field_count,
                    "warning_count": warning_count,
                    "elapsed_seconds": elapsed_seconds,
                    "dataset_annotation_diagnostic": dataset_summary,
                    "files": outcome["files"],
                }
            )
            callback_status = "success"
        except Exception as error:
            difficulty_failure[difficulty] += 1
            sample_results.append(
                {
                    "sample_id": sample_id,
                    "validation_order": sample["validation_order"],
                    "difficulty_group": difficulty,
                    "status": "failed",
                    "error_type": type(error).__name__,
                    "message": safe_error_message(error, secrets),
                }
            )
            callback_status = "failed"
        if progress_callback:
            progress_callback(index, total, sample_id, callback_status)

    success_count = sum(item["status"] == "success" for item in sample_results)
    failure_count = total - success_count
    difficulty_summary = {}
    for difficulty in ("simple", "medium", "complex"):
        group_success = difficulty_success[difficulty]
        difficulty_summary[difficulty] = {
            "successful_sample_count": group_success,
            "failed_sample_count": difficulty_failure[difficulty],
            "total_field_count": difficulty_fields[difficulty],
            "total_warning_count": difficulty_warnings[difficulty],
            "total_elapsed_seconds": round(
                difficulty_elapsed[difficulty], 4
            ),
            "mean_elapsed_seconds": (
                round(difficulty_elapsed[difficulty] / group_success, 4)
                if group_success
                else None
            ),
            "dataset_annotation_diagnostic": _with_dataset_consistency(
                difficulty_dataset_counts[difficulty]
            ),
        }
    finished_at = datetime.now(timezone.utc)
    payload = {
        "metadata": {
            "validation_run_id": validation_run_id,
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "mode": "fixed_engineering_validation",
            "execution": "serial",
            "expected_sample_count": total,
            "field_accuracy_included": False,
            "dataset_annotation_diagnostic_included": True,
        },
        "complete": failure_count == 0 and success_count == total,
        "successful_sample_count": success_count,
        "failed_sample_count": failure_count,
        "samples": sample_results,
        "difficulty_summary": difficulty_summary,
        "engineering_summary": {
            "total_field_count": total_fields,
            "total_warning_count": total_warnings,
            "total_elapsed_seconds": round(total_elapsed, 4),
            "mean_elapsed_seconds": (
                round(total_elapsed / success_count, 4)
                if success_count
                else None
            ),
        },
        "overall_dataset_annotation_diagnostic": _with_dataset_consistency(
            overall_dataset_counts
        ),
    }
    output_path = results_dir / "validations" / f"{validation_run_id}.json"
    write_json_atomic(output_path, payload)
    return {
        "output_path": output_path,
        "output_file": portable_path(output_path, project_root),
        "payload": payload,
    }
