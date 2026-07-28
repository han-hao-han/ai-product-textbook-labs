from __future__ import annotations

import gc
import importlib.metadata
import json
import math
import shutil
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Sequence

from .embedding_config import EmbeddingConfig
from .io_utils import (
    git_blob_sha1,
    read_json,
    sha256_file,
    write_json_atomic,
)
from .paths import EMBEDDING_CONFIG_PATH


class EmbeddingError(RuntimeError):
    """Raised when the frozen local embedding contract cannot be satisfied."""


@dataclass(frozen=True)
class SnapshotDownload:
    snapshot_dir: Path
    attempts: int


def installed_dependency_versions(
    config: EmbeddingConfig,
) -> dict[str, str]:
    versions: dict[str, str] = {}
    missing: list[str] = []
    mismatched: list[str] = []
    for distribution, expected in config.runtime_dependencies.items():
        try:
            actual = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            missing.append(distribution)
            continue
        versions[distribution] = actual
        if actual != expected:
            mismatched.append(f"{distribution}: expected={expected}, actual={actual}")
    if missing or mismatched:
        details: list[str] = []
        if missing:
            details.append(f"缺少依赖：{', '.join(sorted(missing))}")
        details.extend(mismatched)
        raise EmbeddingError(
            "Embedding依赖未满足冻结版本；"
            + "；".join(details)
            + "。请运行：python -m pip install -r requirements.txt"
        )
    return versions


def ensure_embedding_config_snapshot(run_dir: Path) -> Path:
    target = run_dir / "config_snapshot" / "embedding_config.json"
    current = read_json(EMBEDDING_CONFIG_PATH)
    if target.is_file():
        if read_json(target) != current:
            raise EmbeddingError("运行目录中的Embedding配置快照与当前配置不一致")
        return target
    material_model_entries = [
        path
        for path in (run_dir / "model").iterdir()
        if path.name != "failures"
    ]
    if material_model_entries:
        raise EmbeddingError("model目录已有产物但缺少Embedding配置快照")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(EMBEDDING_CONFIG_PATH, target)
    return target


def verify_required_model_files(
    snapshot_dir: Path,
    config: EmbeddingConfig,
) -> list[dict[str, Any]]:
    verified: list[dict[str, Any]] = []
    for expected in config.required_files:
        path = snapshot_dir / expected.path
        if not path.is_file():
            raise EmbeddingError(f"模型缓存缺少必要文件：{expected.path}")
        actual_size = path.stat().st_size
        if actual_size != expected.size_bytes:
            raise EmbeddingError(
                f"模型文件大小不匹配：{expected.path}，"
                f"expected={expected.size_bytes}, actual={actual_size}"
            )
        actual_sha256 = sha256_file(path)
        actual_git_blob_sha1 = None
        if expected.sha256 and actual_sha256 != expected.sha256:
            raise EmbeddingError(
                f"模型文件SHA-256不匹配：{expected.path}"
            )
        if expected.git_blob_sha1:
            actual_git_blob_sha1 = git_blob_sha1(path.read_bytes())
            if actual_git_blob_sha1 != expected.git_blob_sha1:
                raise EmbeddingError(
                    f"模型文件Git blob SHA-1不匹配：{expected.path}"
                )
        verified.append(
            {
                "path": expected.path,
                "size_bytes": actual_size,
                "sha256": actual_sha256,
                "git_blob_sha1": actual_git_blob_sha1,
            }
        )
    return verified


def normalize_query(query: str) -> str:
    normalized = query.replace("\r\n", "\n").replace("\r", "\n").strip()
    while "\n\n\n" in normalized:
        normalized = normalized.replace("\n\n\n", "\n\n")
    if not normalized:
        raise ValueError("查询不能为空")
    return normalized


def validate_embedding_matrix(
    matrix: Any,
    expected_rows: int,
    config: EmbeddingConfig,
) -> dict[str, float]:
    import numpy as np

    if not isinstance(matrix, np.ndarray):
        raise EmbeddingError("Embedding结果必须是NumPy数组")
    if matrix.shape != (expected_rows, config.dimension):
        raise EmbeddingError(
            "Embedding矩阵形状不匹配："
            f"expected={(expected_rows, config.dimension)}, actual={matrix.shape}"
        )
    if matrix.dtype != np.float32:
        raise EmbeddingError(
            f"Embedding dtype必须为float32，实际为{matrix.dtype}"
        )
    if not np.isfinite(matrix).all():
        raise EmbeddingError("Embedding包含NaN或Infinity")
    norms = np.linalg.norm(matrix, axis=1)
    max_deviation = float(np.max(np.abs(norms - 1.0)))
    if max_deviation > 1e-5:
        raise EmbeddingError(
            f"Embedding未通过L2归一化检查：max_deviation={max_deviation}"
        )
    return {
        "min_l2_norm": float(norms.min()),
        "max_l2_norm": float(norms.max()),
        "max_l2_deviation": max_deviation,
    }


class TransformerEmbeddingBackend:
    def __init__(
        self,
        snapshot_dir: Path,
        config: EmbeddingConfig,
        device: str,
    ) -> None:
        import torch
        from transformers import AutoModel, AutoTokenizer

        if device == "cpu":
            torch_device = torch.device("cpu")
        elif device.startswith("cuda:"):
            if not torch.cuda.is_available():
                raise EmbeddingError("运行冻结为CUDA，但当前CUDA不可用")
            index = int(device.split(":", maxsplit=1)[1])
            if index >= torch.cuda.device_count():
                raise EmbeddingError(f"运行冻结设备不存在：{device}")
            torch_device = torch.device(device)
        else:
            raise EmbeddingError(f"不支持的冻结设备：{device}")

        self.torch = torch
        self.config = config
        self.device = device
        self.tokenizer = AutoTokenizer.from_pretrained(
            str(snapshot_dir),
            local_files_only=True,
            trust_remote_code=False,
            padding_side=config.padding_side,
        )
        self.model = AutoModel.from_pretrained(
            str(snapshot_dir),
            local_files_only=True,
            trust_remote_code=False,
            torch_dtype=torch.float32,
        )
        self.model.to(torch_device)
        self.model.eval()
        self.torch_device = torch_device

    def _encode(
        self,
        texts: Sequence[str],
        batch_size: int,
    ) -> tuple[Any, dict[str, Any]]:
        import numpy as np

        if not texts:
            raise ValueError("Embedding输入不能为空")
        token_lengths: list[int] = []
        vectors: list[Any] = []
        started = time.perf_counter()
        for start in range(0, len(texts), batch_size):
            batch_texts = list(texts[start : start + batch_size])
            raw_tokens = self.tokenizer(
                batch_texts,
                add_special_tokens=True,
                padding=False,
                truncation=False,
            )["input_ids"]
            lengths = [len(item) for item in raw_tokens]
            token_lengths.extend(lengths)
            if max(lengths) > self.config.max_length:
                raise EmbeddingError(
                    "Embedding输入超过冻结max_length，拒绝静默截断："
                    f"max={max(lengths)}, limit={self.config.max_length}"
                )
            encoded = self.tokenizer(
                batch_texts,
                padding=True,
                truncation=True,
                max_length=self.config.max_length,
                return_tensors="pt",
            )
            encoded = {
                key: value.to(self.torch_device)
                for key, value in encoded.items()
            }
            with self.torch.no_grad():
                outputs = self.model(**encoded)
                hidden = outputs.last_hidden_state
                attention_mask = encoded["attention_mask"]
                if bool(
                    (attention_mask[:, -1].sum() == attention_mask.shape[0]).item()
                ):
                    pooled = hidden[:, -1]
                else:
                    sequence_lengths = attention_mask.sum(dim=1) - 1
                    pooled = hidden[
                        self.torch.arange(
                            hidden.shape[0],
                            device=hidden.device,
                        ),
                        sequence_lengths,
                    ]
                normalized = self.torch.nn.functional.normalize(
                    pooled,
                    p=2,
                    dim=1,
                )
            vectors.append(
                normalized.detach().to(self.torch.float32).cpu().numpy()
            )
        matrix = np.concatenate(vectors, axis=0).astype(np.float32, copy=False)
        diagnostics = {
            "input_count": len(texts),
            "min_input_tokens": min(token_lengths),
            "max_input_tokens": max(token_lengths),
            "truncated_input_count": 0,
            "elapsed_seconds": round(time.perf_counter() - started, 6),
        }
        diagnostics.update(
            validate_embedding_matrix(matrix, len(texts), self.config)
        )
        return matrix, diagnostics

    def encode_documents(
        self,
        documents: Sequence[str],
        batch_size: int,
    ) -> tuple[Any, dict[str, Any]]:
        return self._encode(documents, batch_size)

    def encode_queries(
        self,
        queries: Sequence[str],
        batch_size: int,
    ) -> tuple[Any, dict[str, Any]]:
        formatted = [
            self.config.format_query(normalize_query(query))
            for query in queries
        ]
        return self._encode(formatted, batch_size)

    def close(self) -> None:
        del self.model
        del self.tokenizer
        gc.collect()
        if self.device.startswith("cuda:"):
            self.torch.cuda.empty_cache()


def _download_snapshot_once(config: EmbeddingConfig) -> Path:
    from huggingface_hub import snapshot_download

    path = snapshot_download(
        repo_id=config.model_id,
        revision=config.revision,
        allow_patterns=[item.path for item in config.required_files],
        local_files_only=False,
    )
    return Path(path)


def _is_retryable_download_error(error: BaseException) -> bool:
    retryable_names = {
        "ChunkedEncodingError",
        "ConnectTimeout",
        "ConnectionError",
        "IncompleteRead",
        "ProtocolError",
        "ReadTimeout",
        "Timeout",
    }
    visited: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        if type(current).__name__ in retryable_names:
            return True
        current = current.__cause__ or current.__context__
    return False


def _snapshot_download(
    config: EmbeddingConfig,
    *,
    download_once: Callable[[EmbeddingConfig], Path] = _download_snapshot_once,
    sleep: Callable[[float], None] = time.sleep,
    max_attempts: int = 3,
) -> SnapshotDownload:
    if max_attempts <= 0:
        raise ValueError("模型下载最大尝试次数必须为正整数")
    for attempt in range(1, max_attempts + 1):
        try:
            return SnapshotDownload(
                snapshot_dir=download_once(config),
                attempts=attempt,
            )
        except Exception as error:
            if (
                attempt >= max_attempts
                or not _is_retryable_download_error(error)
            ):
                raise
            sleep(float(2 ** (attempt - 1)))
    raise AssertionError("不可达的模型下载重试状态")


def _record_model_failure(
    run_dir: Path,
    config: EmbeddingConfig,
    error: Exception,
) -> Path:
    directory = run_dir / "model" / "failures"
    directory.mkdir(parents=True, exist_ok=True)
    existing = sorted(directory.glob("failure_*.json"))
    path = directory / f"failure_{len(existing) + 1:03d}.json"
    message = str(error).replace(str(Path.home()), "<USER_HOME>")
    write_json_atomic(
        path,
        {
            "schema_version": "embedding_failure_v1",
            "experiment_run_id": run_dir.name,
            "failed_at": datetime.now().astimezone().isoformat(),
            "error_type": type(error).__name__,
            "error_message": message,
            "model_id": config.model_id,
            "revision": config.revision,
        },
    )
    return path


def prepare_embedding_model(
    run_dir: Path,
    config: EmbeddingConfig,
    frozen_device: str,
    *,
    downloader: Callable[
        [EmbeddingConfig],
        Path | SnapshotDownload,
    ] = _snapshot_download,
    backend_factory: Callable[
        [Path, EmbeddingConfig, str],
        TransformerEmbeddingBackend,
    ] = TransformerEmbeddingBackend,
) -> dict[str, Any]:
    result_path = run_dir / "model" / "embedding_model.json"
    if result_path.exists():
        raise FileExistsError("Embedding模型准备结果已存在，拒绝覆盖")
    try:
        ensure_embedding_config_snapshot(run_dir)
        dependencies = installed_dependency_versions(config)
        corpus_manifest_path = run_dir / "corpus" / "corpus_manifest.json"
        chunks_path = run_dir / "corpus" / "chunks.jsonl"
        if not corpus_manifest_path.is_file() or not chunks_path.is_file():
            raise FileNotFoundError("缺少检查点1语料，请先完成build_corpus.py")
        corpus_manifest = read_json(corpus_manifest_path)
        with chunks_path.open("r", encoding="utf-8") as handle:
            first_line = handle.readline()
        if not first_line:
            raise EmbeddingError("chunks.jsonl为空")
        first_chunk = json.loads(first_line)

        started = time.perf_counter()
        download_result = downloader(config)
        if isinstance(download_result, SnapshotDownload):
            snapshot_dir = download_result.snapshot_dir
            download_attempts = download_result.attempts
        else:
            snapshot_dir = Path(download_result)
            download_attempts = 1
        files = verify_required_model_files(snapshot_dir, config)
        backend = backend_factory(snapshot_dir, config, frozen_device)
        try:
            batch_size = config.batch_size_for(frozen_device)
            document_matrix, document_test = backend.encode_documents(
                [first_chunk["content"]],
                batch_size,
            )
            query_matrix, query_test = backend.encode_queries(
                [config.demo_query],
                batch_size,
            )
            similarity = float(document_matrix[0] @ query_matrix[0])
            if not math.isfinite(similarity):
                raise EmbeddingError("文档与查询测试相似度不是有限数")
        finally:
            backend.close()
        result = {
            "schema_version": "embedding_model_preparation_v1",
            "experiment_run_id": run_dir.name,
            "prepared_at": datetime.now().astimezone().isoformat(),
            "status": "passed",
            "model_id": config.model_id,
            "revision": config.revision,
            "revision_last_modified": config.revision_last_modified,
            "license": config.license,
            "cache_strategy": "huggingface_shared_cache",
            "local_files_only_after_prepare": True,
            "download_attempts": download_attempts,
            "device": frozen_device,
            "batch_size": config.batch_size_for(frozen_device),
            "dimension": config.dimension,
            "inference_dtype": config.inference_dtype,
            "storage_dtype": config.storage_dtype,
            "pooling": config.pooling,
            "normalization": config.normalize,
            "max_length": config.max_length,
            "query_instruction": config.query_instruction,
            "query_template": config.query_template,
            "document_instruction": None,
            "dependencies": dependencies,
            "required_files": files,
            "document_embedding_test": document_test,
            "query_embedding_test": query_test,
            "document_query_similarity_smoke_test": similarity,
            "corpus_sha256": corpus_manifest["corpus_sha256"],
            "elapsed_seconds": round(time.perf_counter() - started, 6),
        }
        write_json_atomic(result_path, result)
        return result
    except Exception as error:
        try:
            _record_model_failure(run_dir, config, error)
        except OSError:
            pass
        raise
