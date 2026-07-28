from __future__ import annotations

from pathlib import Path

import pytest

from src.example_export import (
    ExampleExportError,
    build_example_candidates,
    export_checkpoint_examples,
)
from src.io_utils import read_json, write_json_atomic


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _fake_run(tmp_path: Path) -> Path:
    run_dir = tmp_path / "runs" / "fastapi_rag_test"
    for index in range(1, 5):
        checkpoint = f"checkpoint_{index}"
        report = {
            "schema_version": f"{checkpoint}_report_v1",
            "experiment_run_id": run_dir.name,
            "status": "passed" if index == 3 else "warning",
        }
        if index == 3:
            report["reader_experience_records"] = [
                {
                    "reader_experience_type": kind,
                    "saved_result": (
                        f"interactive/saved/result_{position:03d}/result.json"
                    ),
                }
                for position, kind in enumerate(
                    ("in_scope", "boundary", "out_of_scope"),
                    start=1,
                )
            ]
        directory = run_dir / "checkpoints" / checkpoint
        write_json_atomic(directory / "report.json", report)
        _write_text(directory / "report.md", f"# {checkpoint}\n")

    for position in range(1, 4):
        saved = run_dir / "interactive" / "saved" / f"result_{position:03d}"
        for name in (
            "result.json",
            "retrieval_results.json",
            "generation_context.json",
            "snapshot_metadata.json",
        ):
            write_json_atomic(saved / name, {"safe": True, "position": position})
        _write_text(saved / "result.md", "# 真实现场结果\n")

    included = []
    judge_records = []
    for question_id, grade in (
        ("EVAL_IN_001", "fully_correct"),
        ("EVAL_IN_002", "mostly_correct"),
    ):
        input_path = run_dir / "judge" / "inputs_v1" / f"{question_id}.json"
        write_json_atomic(
            input_path,
            {
                "question_id": question_id,
                "question": "如何测试？",
                "required_points": ["必答点"],
                "optional_points": [],
                "critical_errors": [],
                "final_answer": "这是经过校验的回答。",
                "cited_chunks": [
                    {
                        "chunk_id": "chunk_001",
                        "source_path": "docs/zh/docs/tutorial/testing.md",
                        "section_path": ["测试"],
                        "content": "安全证据。",
                    }
                ],
            },
        )
        included.append(
            {
                "question_id": question_id,
                "input_path": (
                    f"judge/inputs_v1/{question_id}.json"
                ),
            }
        )
        attempt_path = f"judge/formal/{question_id}/attempt_001"
        attempt_dir = run_dir / attempt_path
        write_json_atomic(
            attempt_dir / "metadata.json",
            {
                "question_id": question_id,
                "attempt": "attempt_001",
                "formal_evaluation": True,
                "status": "judged",
                "forbidden_events": [],
                "model": "gpt-5.6-sol",
                "reasoning_effort": "medium",
                "cli_version": "0.145.0",
                "sandbox": "read-only",
                "ephemeral": True,
                "automatic_retries": 0,
                "input_sha256": "a" * 64,
                "prompt_sha256": "b" * 64,
                "credential_saved": False,
            },
        )
        write_json_atomic(
            attempt_dir / "parsed_output.json",
            {
                "answer_grade": grade,
                "covered_required_points": ["必答点"],
                "missing_required_points": [],
                "critical_errors": [],
                "unsupported_major_claim": False,
                "citation_supports_answer": True,
                "citation_set_minimal": True,
                "review_reason": "真实首次审核。",
            },
        )
        judge_records.append(
            {
                "question_id": question_id,
                "status": "judged",
                "answer_grade": grade,
                "attempt_path": attempt_path,
            }
        )
    write_json_atomic(
        run_dir / "judge" / "inputs_v1" / "manifest.json",
        {"status": "passed", "included": included},
    )
    write_json_atomic(
        run_dir / "judge" / "formal" / "summary.json",
        {
            "status": "passed",
            "formal_metrics_attempt": "attempt_001",
            "records": judge_records,
        },
    )
    return run_dir


def test_build_candidates_and_export_same_run_chain(tmp_path: Path) -> None:
    run_dir = _fake_run(tmp_path)
    candidate_root = tmp_path / "candidates"
    target_dir = tmp_path / "public" / "examples"

    candidate_dir = build_example_candidates(
        run_dir,
        candidate_root=candidate_root,
    )
    manifest = read_json(candidate_dir / "candidate_manifest.json")

    assert manifest["status"] == "pending_human_confirmation"
    assert [item["answer_grade"] for item in manifest["judge_candidates"]] == [
        "fully_correct",
        "mostly_correct",
    ]
    assert not target_dir.exists()

    exported = export_checkpoint_examples(
        run_dir,
        candidate_root=candidate_root,
        target_dir=target_dir,
    )
    public_manifest = read_json(exported / "manifest.json")

    assert public_manifest["same_run_chain"] is True
    assert public_manifest["contains_api_key"] is False
    assert (exported / "README.md").is_file()
    assert (
        exported
        / "checkpoint_3"
        / "interactive"
        / "in_scope"
        / "result.json"
    ).is_file()
    assert (
        exported
        / "checkpoint_4"
        / "judge_examples"
        / "EVAL_IN_002.json"
    ).is_file()
    with pytest.raises(FileExistsError, match="拒绝覆盖"):
        export_checkpoint_examples(
            run_dir,
            candidate_root=candidate_root,
            target_dir=target_dir,
        )


def test_candidate_build_rejects_local_absolute_path(tmp_path: Path) -> None:
    run_dir = _fake_run(tmp_path)
    _write_text(
        run_dir / "checkpoints" / "checkpoint_1" / "report.md",
        f"本地路径：{Path.home() / 'private' / 'result.json'}\n",
    )

    with pytest.raises(ExampleExportError, match="本地绝对路径"):
        build_example_candidates(
            run_dir,
            candidate_root=tmp_path / "candidates",
        )
