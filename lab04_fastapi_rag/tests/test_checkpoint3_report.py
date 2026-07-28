from __future__ import annotations

from src.checkpoint3_report import build_checkpoint3_report
from src.io_utils import read_json, write_json_atomic


def _save_result(run_dir, number, kind, state):
    directory = (
        run_dir / "interactive" / "saved" / f"result_{number:03d}"
    )
    write_json_atomic(
        directory / "result.json",
        {
            "reader_experience_type": kind,
            "question": f"{kind} question",
            "final_state": state,
            "top_k": 5,
            "total_elapsed_seconds": 1.0,
        },
    )


def test_checkpoint3_report_requires_three_reader_types(tmp_path) -> None:
    _save_result(tmp_path, 1, "in_scope", "answered")

    try:
        build_checkpoint3_report(tmp_path)
    except ValueError as error:
        assert "缺少" in str(error)
    else:
        raise AssertionError("missing reader types must fail")


def test_checkpoint3_report_passes_valid_three_type_experience(
    tmp_path,
) -> None:
    _save_result(tmp_path, 1, "in_scope", "answered")
    _save_result(tmp_path, 2, "boundary", "model_refused")
    _save_result(tmp_path, 3, "out_of_scope", "retrieval_rejected")
    write_json_atomic(
        tmp_path / "generation" / "current_state.json",
        {
            "schema_version": "generation_current_state_v1",
            "status": "passed",
            "latest_attempt": "attempt_001",
        },
    )

    report_md, report_json = build_checkpoint3_report(tmp_path)
    report = read_json(report_json)

    assert report["status"] == "passed"
    assert len(report["reader_experience_records"]) == 3
    assert report["formal_evaluation_run"] is False
    assert "未运行30道正式题" in report_md.read_text(encoding="utf-8")
