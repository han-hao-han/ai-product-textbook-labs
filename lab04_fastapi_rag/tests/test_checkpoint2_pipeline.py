from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from src.checkpoint2_report import write_checkpoint2_report
from src.embedding_config import load_embedding_config
from src.index_builder import build_index, chunk_order_sha256
from src.io_utils import write_json_atomic
from src.retriever import retrieve_top_k


class FakeBackend:
    def __init__(self, snapshot_dir: Path, config, device: str) -> None:
        self.config = config
        self.closed = False

    def encode_documents(self, documents, batch_size: int):
        matrix = np.zeros(
            (len(documents), self.config.dimension),
            dtype=np.float32,
        )
        for index in range(len(documents)):
            matrix[index, index] = 1.0
        return matrix, {
            "input_count": len(documents),
            "min_input_tokens": 4,
            "max_input_tokens": 8,
            "truncated_input_count": 0,
            "elapsed_seconds": 0.01,
            "min_l2_norm": 1.0,
            "max_l2_norm": 1.0,
            "max_l2_deviation": 0.0,
        }

    def encode_queries(self, queries, batch_size: int):
        matrix = np.zeros((1, self.config.dimension), dtype=np.float32)
        matrix[0, 2] = 1.0
        return matrix, {
            "input_count": 1,
            "min_input_tokens": 5,
            "max_input_tokens": 5,
            "truncated_input_count": 0,
            "elapsed_seconds": 0.01,
            "min_l2_norm": 1.0,
            "max_l2_norm": 1.0,
            "max_l2_deviation": 0.0,
        }

    def close(self) -> None:
        self.closed = True


def _make_run(tmp_path: Path) -> tuple[Path, list[dict]]:
    run_dir = tmp_path / "fastapi_rag_20260728_010203_abcdef"
    for relative in ("model", "corpus", "index", "checkpoints"):
        (run_dir / relative).mkdir(parents=True)
    chunks = []
    for index in range(5):
        content = f"测试Chunk {index}"
        chunks.append(
            {
                "chunk_id": f"chunk-{index}",
                "page_title": f"页面 {index}",
                "section_path": ["章节", str(index)],
                "section_paths": [["章节", str(index)]],
                "source_path": f"docs/zh/docs/tutorial/page_{index}.md",
                "source_url": f"https://example.test/page_{index}",
                "chunk_index": index,
                "token_count": 10,
                "contains_code": False,
                "contains_table": False,
                "content_sha256": f"{index:064x}",
                "content": content,
            }
        )
    chunks_text = "".join(
        json.dumps(chunk, ensure_ascii=False) + "\n" for chunk in chunks
    )
    (run_dir / "corpus" / "chunks.jsonl").write_text(
        chunks_text,
        encoding="utf-8",
    )
    corpus_hash = chunk_order_sha256(chunks)
    write_json_atomic(
        run_dir / "corpus" / "corpus_manifest.json",
        {
            "status": "warning",
            "chunk_count": len(chunks),
            "corpus_sha256": corpus_hash,
        },
    )
    config = load_embedding_config()
    write_json_atomic(
        run_dir / "model" / "embedding_model.json",
        {
            "status": "passed",
            "revision": config.revision,
            "corpus_sha256": corpus_hash,
            "device": "cpu",
            "dimension": config.dimension,
            "pooling": config.pooling,
            "normalization": config.normalize,
        },
    )
    return run_dir, chunks


def test_index_retrieval_and_report_are_exact_and_atomic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir, chunks = _make_run(tmp_path)
    config = load_embedding_config()
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    dependencies = config.runtime_dependencies
    monkeypatch.setattr(
        "src.index_builder.installed_dependency_versions",
        lambda unused: dependencies,
    )
    monkeypatch.setattr(
        "src.index_builder.verify_required_model_files",
        lambda unused_path, unused_config: [],
    )
    monkeypatch.setattr(
        "src.retriever.installed_dependency_versions",
        lambda unused: dependencies,
    )
    monkeypatch.setattr(
        "src.retriever.verify_required_model_files",
        lambda unused_path, unused_config: [],
    )

    index = build_index(
        run_dir,
        config,
        "cpu",
        snapshot_locator=lambda unused: snapshot,
        backend_factory=FakeBackend,
    )
    result = retrieve_top_k(
        run_dir,
        config,
        "cpu",
        config.demo_query,
        snapshot_locator=lambda unused: snapshot,
        backend_factory=FakeBackend,
    )
    report_md, report_json, demo_json = write_checkpoint2_report(
        run_dir,
        config,
        result,
    )

    assert index["matrix_shape"] == [5, 1024]
    assert index["matrix_dtype"] == "float32"
    assert index["chunk_order_sha256"] == chunk_order_sha256(chunks)
    assert result["hits"][0]["chunk_id"] == "chunk-2"
    assert result["hits"][0]["score"] == pytest.approx(1.0)
    assert [hit["chunk_id"] for hit in result["hits"][1:]] == [
        "chunk-0",
        "chunk-1",
        "chunk-3",
        "chunk-4",
    ]
    assert result["generation_model_called"] is False
    assert report_md.is_file()
    assert report_json.is_file()
    assert demo_json.is_file()
    assert not list((run_dir / "checkpoints").glob(".checkpoint_2.*"))
    with pytest.raises(FileExistsError, match="拒绝覆盖"):
        write_checkpoint2_report(run_dir, config, result)
