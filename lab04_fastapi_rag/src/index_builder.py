from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .embedding_config import EmbeddingConfig
from .embedding_model import (
    EmbeddingError,
    TransformerEmbeddingBackend,
    installed_dependency_versions,
    validate_embedding_matrix,
    verify_required_model_files,
)
from .io_utils import (
    read_json,
    sha256_file,
    sha256_text,
    write_json_atomic,
    write_text_atomic,
)


class IndexBuildError(RuntimeError):
    """Raised when the exact NumPy index cannot be built safely."""


def chunk_order_sha256(chunks: list[dict[str, Any]]) -> str:
    return sha256_text(
        "\n".join(
            f"{chunk['chunk_id']}:{chunk['content_sha256']}"
            for chunk in chunks
        )
    )


def _local_snapshot(config: EmbeddingConfig) -> Path:
    from huggingface_hub import snapshot_download

    try:
        path = snapshot_download(
            repo_id=config.model_id,
            revision=config.revision,
            allow_patterns=[item.path for item in config.required_files],
            local_files_only=True,
        )
    except Exception as error:
        raise EmbeddingError(
            "共享缓存缺少冻结模型；请重新运行prepare_embedding_model.py"
        ) from error
    return Path(path)


def _record_index_failure(
    run_dir: Path,
    config: EmbeddingConfig,
    error: Exception,
) -> Path:
    directory = run_dir / "index" / "failures"
    directory.mkdir(parents=True, exist_ok=True)
    existing = sorted(directory.glob("failure_*.json"))
    path = directory / f"failure_{len(existing) + 1:03d}.json"
    message = str(error).replace(str(Path.home()), "<USER_HOME>")
    write_json_atomic(
        path,
        {
            "schema_version": "index_failure_v1",
            "experiment_run_id": run_dir.name,
            "failed_at": datetime.now().astimezone().isoformat(),
            "error_type": type(error).__name__,
            "error_message": message,
            "model_id": config.model_id,
            "revision": config.revision,
        },
    )
    return path


def build_index(
    run_dir: Path,
    config: EmbeddingConfig,
    frozen_device: str,
    *,
    snapshot_locator: Callable[[EmbeddingConfig], Path] = _local_snapshot,
    backend_factory: Callable[
        [Path, EmbeddingConfig, str],
        TransformerEmbeddingBackend,
    ] = TransformerEmbeddingBackend,
) -> dict[str, Any]:
    import numpy as np

    index_dir = run_dir / "index"
    current_dir = index_dir / "current"
    if current_dir.exists():
        raise FileExistsError("index/current已存在，拒绝覆盖")
    model_record_path = run_dir / "model" / "embedding_model.json"
    corpus_manifest_path = run_dir / "corpus" / "corpus_manifest.json"
    chunks_path = run_dir / "corpus" / "chunks.jsonl"
    if not model_record_path.is_file():
        raise FileNotFoundError(
            "缺少embedding_model.json，请先运行prepare_embedding_model.py"
        )
    if not corpus_manifest_path.is_file() or not chunks_path.is_file():
        raise FileNotFoundError("缺少检查点1语料")
    model_record = read_json(model_record_path)
    corpus_manifest = read_json(corpus_manifest_path)
    if (
        model_record.get("status") != "passed"
        or model_record.get("revision") != config.revision
    ):
        raise IndexBuildError("Embedding模型准备记录与冻结Revision不兼容")
    if model_record.get("corpus_sha256") != corpus_manifest.get("corpus_sha256"):
        raise IndexBuildError("模型准备记录与当前语料哈希不一致")

    chunks_text = chunks_path.read_text(encoding="utf-8")
    chunks = [
        json.loads(line)
        for line in chunks_text.splitlines()
        if line.strip()
    ]
    if len(chunks) != int(corpus_manifest["chunk_count"]):
        raise IndexBuildError("Chunk数量与corpus_manifest不一致")
    if len({chunk["chunk_id"] for chunk in chunks}) != len(chunks):
        raise IndexBuildError("Chunk ID不唯一")

    staging_dir = Path(
        tempfile.mkdtemp(prefix=".build.", dir=index_dir)
    )
    backend = None
    try:
        started = time.perf_counter()
        dependencies = installed_dependency_versions(config)
        snapshot_dir = snapshot_locator(config)
        verify_required_model_files(snapshot_dir, config)
        backend = backend_factory(snapshot_dir, config, frozen_device)
        batch_size = config.batch_size_for(frozen_device)
        matrix, diagnostics = backend.encode_documents(
            [str(chunk["content"]) for chunk in chunks],
            batch_size,
        )
        norm_diagnostics = validate_embedding_matrix(
            matrix,
            len(chunks),
            config,
        )
        embeddings_path = staging_dir / "embeddings.npy"
        with embeddings_path.open("wb") as handle:
            np.save(handle, matrix, allow_pickle=False)
        metadata_path = staging_dir / "chunk_metadata.jsonl"
        write_text_atomic(metadata_path, chunks_text)
        order_hash = chunk_order_sha256(chunks)
        if order_hash != corpus_manifest["corpus_sha256"]:
            raise IndexBuildError("Chunk顺序哈希与语料哈希不一致")
        summary = {
            "schema_version": "numpy_embedding_index_v1",
            "experiment_run_id": run_dir.name,
            "built_at": datetime.now().astimezone().isoformat(),
            "status": "passed",
            "model_id": config.model_id,
            "revision": config.revision,
            "device": frozen_device,
            "batch_size": batch_size,
            "matrix_shape": list(matrix.shape),
            "matrix_dtype": str(matrix.dtype),
            "dimension": config.dimension,
            "normalization": config.normalize,
            "similarity": "exact_cosine_via_dot_product_on_l2_vectors",
            "chunk_count": len(chunks),
            "chunk_order_sha256": order_hash,
            "corpus_sha256": corpus_manifest["corpus_sha256"],
            "embeddings_file": "index/current/embeddings.npy",
            "embeddings_sha256": sha256_file(embeddings_path),
            "metadata_file": "index/current/chunk_metadata.jsonl",
            "metadata_sha256": sha256_file(metadata_path),
            "embedding_diagnostics": diagnostics,
            "norm_diagnostics": norm_diagnostics,
            "dependencies": dependencies,
            "group_chunk_counts": dict(
                sorted(
                    Counter(
                        str(chunk["source_path"]).split("/")[3]
                        for chunk in chunks
                    ).items()
                )
            ),
            "elapsed_seconds": round(time.perf_counter() - started, 6),
        }
        write_json_atomic(staging_dir / "index_manifest.json", summary)
        os.replace(staging_dir, current_dir)
        return summary
    except Exception as error:
        shutil.rmtree(staging_dir, ignore_errors=True)
        try:
            _record_index_failure(run_dir, config, error)
        except OSError:
            pass
        raise
    finally:
        if backend is not None:
            backend.close()
