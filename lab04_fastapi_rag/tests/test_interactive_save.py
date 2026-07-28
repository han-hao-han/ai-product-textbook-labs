from __future__ import annotations

import json

import pytest

from src.interactive_save import save_interactive_result


def _result() -> dict:
    return {
        "schema_version": "interactive_rag_result_v1",
        "experiment_run_id": "run",
        "created_at": "2026-07-28T00:00:00+08:00",
        "question": "如何处理404？",
        "top_k": 5,
        "threshold": 0.6831968426704407,
        "phases": [],
        "final_state": "answered",
        "total_elapsed_seconds": 1.0,
        "answer": {
            "answerable": True,
            "answer": "使用HTTPException。",
            "cited_chunk_ids": ["chunk_1"],
            "refusal_reason": None,
        },
        "citations": [],
        "validation_warnings": [],
        "retrieval": {"hits": []},
        "generation": {
            "online_model_called": True,
            "evidence_sent": [],
            "raw_responses": [{"content": '{"answerable":true}'}],
        },
    }


def test_save_requires_explicit_confirmation(tmp_path) -> None:
    with pytest.raises(ValueError, match="显式确认"):
        save_interactive_result(tmp_path, _result(), confirmed=False)


def test_save_writes_five_separated_artifacts_without_key(tmp_path) -> None:
    path = save_interactive_result(tmp_path, _result(), confirmed=True)

    assert {item.name for item in path.iterdir()} == {
        "result.json",
        "result.md",
        "retrieval_results.json",
        "generation_context.json",
        "snapshot_metadata.json",
    }
    combined = "\n".join(
        item.read_text(encoding="utf-8") for item in path.iterdir()
    )
    assert "DASHSCOPE_API_KEY" not in combined
    context = json.loads(
        (path / "generation_context.json").read_text(encoding="utf-8")
    )
    assert context["raw_responses"]
    assert context["api_key_saved"] is False
