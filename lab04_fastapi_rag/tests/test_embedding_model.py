from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from src.embedding_config import RequiredModelFile, load_embedding_config
from src.embedding_model import (
    EmbeddingError,
    SnapshotDownload,
    _is_retryable_download_error,
    _snapshot_download,
    installed_dependency_versions,
    normalize_query,
    validate_embedding_matrix,
    verify_required_model_files,
)


class ChunkedEncodingError(Exception):
    pass


def test_transient_model_download_resumes_with_bounded_retry() -> None:
    config = load_embedding_config()
    attempts = 0
    sleeps: list[float] = []

    def download_once(unused_config) -> Path:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ChunkedEncodingError("连接中断")
        return Path("frozen-snapshot")

    result = _snapshot_download(
        config,
        download_once=download_once,
        sleep=sleeps.append,
        max_attempts=3,
    )

    assert result == SnapshotDownload(Path("frozen-snapshot"), 3)
    assert sleeps == [1.0, 2.0]


def test_non_transient_model_download_error_is_not_retried() -> None:
    config = load_embedding_config()
    attempts = 0

    def download_once(unused_config) -> Path:
        nonlocal attempts
        attempts += 1
        raise ValueError("Revision不存在")

    with pytest.raises(ValueError, match="Revision"):
        _snapshot_download(
            config,
            download_once=download_once,
            sleep=lambda unused: None,
        )
    assert attempts == 1
    assert _is_retryable_download_error(ValueError("认证失败")) is False


def test_frozen_embedding_dependencies_are_installed_and_importable() -> None:
    config = load_embedding_config()

    assert installed_dependency_versions(config) == config.runtime_dependencies
    from transformers import AutoModel, AutoTokenizer

    assert AutoModel is not None
    assert AutoTokenizer is not None


def test_query_normalization_only_applies_frozen_rules() -> None:
    query = "  第一行\r\n\r\n\r\n第二行  "

    assert normalize_query(query) == "第一行\n\n第二行"


def test_embedding_matrix_requires_float32_l2_vectors() -> None:
    config = replace(load_embedding_config(), dimension=3)
    matrix = np.asarray([[1.0, 0.0, 0.0]], dtype=np.float32)

    diagnostics = validate_embedding_matrix(matrix, 1, config)

    assert diagnostics["max_l2_deviation"] == 0.0
    with pytest.raises(EmbeddingError, match="float32"):
        validate_embedding_matrix(matrix.astype(np.float64), 1, config)
    with pytest.raises(EmbeddingError, match="L2"):
        validate_embedding_matrix(matrix * 2, 1, config)


def test_required_model_file_sha256_is_verified(tmp_path: Path) -> None:
    content = b"frozen-model-file"
    path = tmp_path / "config.json"
    path.write_bytes(content)
    required = RequiredModelFile(
        path="config.json",
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        git_blob_sha1=None,
    )
    config = replace(load_embedding_config(), required_files=(required,))

    verified = verify_required_model_files(tmp_path, config)

    assert verified[0]["sha256"] == required.sha256
    path.write_bytes(b"tampered-model-xx")
    with pytest.raises(EmbeddingError, match="SHA-256"):
        verify_required_model_files(tmp_path, config)
