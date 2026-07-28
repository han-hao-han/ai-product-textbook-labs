from __future__ import annotations

import os
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .io_utils import read_json, write_json_atomic
from .judge_client import run_judge_attempt
from .judge_config import load_judge_config
from .judge_inputs import load_blind_input
from .paths import JUDGE_FORMAL_DIR_NAME, JUDGE_INPUTS_DIR_NAME


JUDGE_TERMINAL_STATES = {
    "judged",
    "judge_failed",
    "judge_validation_failed",
    "judge_contaminated",
}


class FormalJudgeError(RuntimeError):
    """Raised when formal Judge attempts cannot be resumed safely."""


def _existing_status(attempt_dir: Path, question_id: str) -> str | None:
    if not attempt_dir.exists():
        return None
    metadata_path = attempt_dir / "metadata.json"
    if not metadata_path.is_file():
        raise FormalJudgeError(
            f"{question_id}/attempt_001不完整，拒绝覆盖或自动重试"
        )
    metadata = read_json(metadata_path)
    if (
        metadata.get("question_id") != question_id
        or metadata.get("attempt") != "attempt_001"
        or metadata.get("formal_evaluation") is not True
        or metadata.get("status") not in JUDGE_TERMINAL_STATES
    ):
        raise FormalJudgeError(f"{question_id}/attempt_001元数据无效")
    return str(metadata["status"])


def _summary(run_dir: Path, included: list[dict[str, Any]]) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for item in included:
        question_id = str(item["question_id"])
        attempt_dir = (
            run_dir
            / "judge"
            / JUDGE_FORMAL_DIR_NAME
            / question_id
            / "attempt_001"
        )
        if not (attempt_dir / "metadata.json").is_file():
            continue
        metadata = read_json(attempt_dir / "metadata.json")
        output = (
            read_json(attempt_dir / "parsed_output.json")
            if (attempt_dir / "parsed_output.json").is_file()
            else None
        )
        records.append(
            {
                "question_id": question_id,
                "status": metadata["status"],
                "answer_grade": (
                    output.get("answer_grade")
                    if isinstance(output, dict)
                    else None
                ),
                "attempt_path": (
                    f"judge/{JUDGE_FORMAL_DIR_NAME}/"
                    f"{question_id}/attempt_001"
                ),
            }
        )
    complete = len(records) == len(included)
    status_counts = Counter(item["status"] for item in records)
    return {
        "schema_version": "formal_codex_judge_summary_v1",
        "experiment_run_id": run_dir.name,
        "created_at": datetime.now().astimezone().isoformat(),
        "status": (
            "passed"
            if complete and set(status_counts) <= {"judged"}
            else "warning"
            if complete
            else "blocked"
        ),
        "formal_metrics_attempt": "attempt_001",
        "input_count": len(included),
        "completed_count": len(records),
        "remaining_count": len(included) - len(records),
        "status_counts": dict(status_counts),
        "grade_counts": dict(
            Counter(
                str(item["answer_grade"])
                for item in records
                if item["answer_grade"] is not None
            )
        ),
        "records": records,
    }


def run_formal_judge(
    run_dir: Path,
    *,
    environment: dict[str, str] | None = None,
    progress: Callable[[int, int, str, str], None] | None = None,
) -> dict[str, Any]:
    config = load_judge_config(require_frozen=True)
    manifest_path = (
        run_dir / "judge" / JUDGE_INPUTS_DIR_NAME / "manifest.json"
    )
    if not manifest_path.is_file():
        raise FileNotFoundError("缺少Judge盲审输入manifest")
    manifest = read_json(manifest_path)
    if manifest.get("status") != "passed":
        raise FormalJudgeError("Judge盲审输入状态不是passed")
    included = manifest.get("included")
    if not isinstance(included, list):
        raise FormalJudgeError("Judge盲审输入manifest格式无效")
    env = dict(os.environ if environment is None else environment)
    total = len(included)
    for position, item in enumerate(included, start=1):
        question_id = str(item["question_id"])
        input_path = (
            run_dir / str(item["input_path"])
        )
        attempt_dir = (
            run_dir
            / "judge"
            / JUDGE_FORMAL_DIR_NAME
            / question_id
            / "attempt_001"
        )
        existing = _existing_status(attempt_dir, question_id)
        if existing is not None:
            if progress:
                progress(position, total, question_id, "skipped")
            continue
        blind = load_blind_input(input_path)
        result = run_judge_attempt(
            blind,
            attempt_dir=attempt_dir,
            config=config,
            environment=env,
            formal_evaluation=True,
        )
        if progress:
            progress(
                position,
                total,
                question_id,
                str(result["status"]),
            )
    summary = _summary(run_dir, included)
    output_dir = run_dir / "judge" / JUDGE_FORMAL_DIR_NAME
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json_atomic(output_dir / "summary.json", summary)
    return summary
