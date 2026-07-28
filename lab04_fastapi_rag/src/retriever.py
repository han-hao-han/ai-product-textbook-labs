from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .embedding_config import EmbeddingConfig
from .embedding_model import (
    EmbeddingError,
    TransformerEmbeddingBackend,
    installed_dependency_versions,
    normalize_query,
    validate_embedding_matrix,
    verify_required_model_files,
)
from .index_builder import _local_snapshot, chunk_order_sha256
from .io_utils import read_json, sha256_file


class RetrievalError(RuntimeError):
    """Raised when a frozen index cannot produce an exact Top-k result."""


def load_validated_index(
    run_dir: Path,
    config: EmbeddingConfig,
) -> tuple[Any, list[dict[str, Any]], dict[str, Any]]:
    import numpy as np

    current_dir = run_dir / "index" / "current"
    manifest_path = current_dir / "index_manifest.json"
    matrix_path = current_dir / "embeddings.npy"
    metadata_path = current_dir / "chunk_metadata.jsonl"
    if not manifest_path.is_file():
        raise FileNotFoundError(
            "缺少index_manifest.json，请先运行build_index.py"
        )
    manifest = read_json(manifest_path)
    if manifest.get("status") != "passed":
        raise RetrievalError("索引状态不是passed")
    if manifest.get("model_id") != config.model_id:
        raise RetrievalError("索引模型ID与冻结配置不一致")
    if manifest.get("revision") != config.revision:
        raise RetrievalError("索引模型Revision与冻结配置不一致")
    if manifest.get("dimension") != config.dimension:
        raise RetrievalError("索引维度与冻结配置不一致")
    if manifest.get("normalization") != config.normalize:
        raise RetrievalError("索引归一化方式与冻结配置不一致")
    if sha256_file(matrix_path) != manifest.get("embeddings_sha256"):
        raise RetrievalError("索引矩阵SHA-256不匹配")
    if sha256_file(metadata_path) != manifest.get("metadata_sha256"):
        raise RetrievalError("索引元数据SHA-256不匹配")
    matrix = np.load(matrix_path, allow_pickle=False)
    chunks = [
        json.loads(line)
        for line in metadata_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    validate_embedding_matrix(matrix, len(chunks), config)
    if len(chunks) != manifest.get("chunk_count"):
        raise RetrievalError("索引Chunk数量与manifest不一致")
    if list(matrix.shape) != manifest.get("matrix_shape"):
        raise RetrievalError("索引矩阵形状与manifest不一致")
    if chunk_order_sha256(chunks) != manifest.get("chunk_order_sha256"):
        raise RetrievalError("索引Chunk顺序哈希不一致")
    return matrix, chunks, manifest


def retrieve_top_k(
    run_dir: Path,
    config: EmbeddingConfig,
    frozen_device: str,
    query: str,
    *,
    top_k: int | None = None,
    snapshot_locator: Callable[[EmbeddingConfig], Path] = _local_snapshot,
    backend_factory: Callable[
        [Path, EmbeddingConfig, str],
        TransformerEmbeddingBackend,
    ] = TransformerEmbeddingBackend,
) -> dict[str, Any]:
    import numpy as np

    normalized_query = normalize_query(query)
    requested_top_k = config.top_k if top_k is None else int(top_k)
    if requested_top_k < 1 or requested_top_k > 8:
        raise ValueError("top_k必须位于1～8")
    matrix, chunks, index_manifest = load_validated_index(run_dir, config)
    if len(chunks) < requested_top_k:
        raise RetrievalError("索引Chunk数量少于冻结top_k")
    dependencies = installed_dependency_versions(config)
    snapshot_dir = snapshot_locator(config)
    verify_required_model_files(snapshot_dir, config)
    backend = backend_factory(snapshot_dir, config, frozen_device)
    try:
        started = time.perf_counter()
        query_matrix, query_diagnostics = backend.encode_queries(
            [normalized_query],
            config.batch_size_for(frozen_device),
        )
        query_vector = query_matrix[0]
        scores = matrix @ query_vector
        if not np.isfinite(scores).all():
            raise RetrievalError("相似度包含NaN或Infinity")
        top_indices = np.argsort(-scores, kind="stable")[:requested_top_k]
        hits: list[dict[str, Any]] = []
        for rank, row_index in enumerate(top_indices.tolist(), start=1):
            chunk = chunks[row_index]
            hits.append(
                {
                    "rank": rank,
                    "score": float(scores[row_index]),
                    "row_index": row_index,
                    "chunk_id": chunk["chunk_id"],
                    "page_title": chunk["page_title"],
                    "section_path": chunk["section_path"],
                    "section_paths": chunk["section_paths"],
                    "source_path": chunk["source_path"],
                    "source_url": chunk["source_url"],
                    "chunk_index": chunk["chunk_index"],
                    "token_count": chunk["token_count"],
                    "contains_code": chunk["contains_code"],
                    "contains_table": chunk["contains_table"],
                    "content_sha256": chunk["content_sha256"],
                    "content": chunk["content"],
                }
            )
        result = {
            "schema_version": "retrieval_demo_v1",
            "experiment_run_id": run_dir.name,
            "created_at": datetime.now().astimezone().isoformat(),
            "status": "passed",
            "query": normalized_query,
            "query_instruction": config.query_instruction,
            "query_template": config.query_template,
            "model_id": config.model_id,
            "revision": config.revision,
            "device": frozen_device,
            "top_k": requested_top_k,
            "similarity": index_manifest["similarity"],
            "query_embedding_diagnostics": query_diagnostics,
            "top1_score": hits[0]["score"],
            "hits": hits,
            "dependencies": dependencies,
            "elapsed_seconds": round(time.perf_counter() - started, 6),
            "generation_model_called": False,
        }
        return result
    finally:
        backend.close()
