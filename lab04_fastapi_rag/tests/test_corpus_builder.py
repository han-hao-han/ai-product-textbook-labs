from __future__ import annotations

import json
from pathlib import Path

from src.corpus_builder import build_corpus
from src.document_manifest import build_document_manifest


def test_corpus_records_chunk_distribution_and_reasons(
    tmp_path: Path,
    frozen_repo,
) -> None:
    repo_root, config = frozen_repo
    run_dir = tmp_path / "run"
    source_dir = run_dir / "source"
    source_dir.mkdir(parents=True)
    (run_dir / "corpus").mkdir()
    repo_root.rename(source_dir / "repository")
    build_document_manifest(run_dir, config)

    manifest = build_corpus(run_dir, config)

    assert manifest["schema_version"] == "fastapi_corpus_v2"
    assert manifest["document_count"] == 102
    assert manifest["chunk_count"] > 0
    assert (
        manifest["chunks_in_target_range"]
        + manifest["chunks_under_target_min"]
        + manifest["chunks_over_target_max"]
        == manifest["chunk_count"]
    )
    assert sum(manifest["under_min_reason_counts"].values()) == (
        manifest["chunks_under_target_min"]
    )
    assert sum(manifest["over_max_reason_counts"].values()) == (
        manifest["chunks_over_target_max"]
    )
    first_chunk = json.loads(
        (run_dir / "corpus" / "chunks.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()[0]
    )
    assert first_chunk["content"].startswith("# ")
    assert first_chunk["section_paths"]
    assert "chunk_boundary_reason" in first_chunk
