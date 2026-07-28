from __future__ import annotations

import json
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any

from .chunker import chunk_document
from .io_utils import read_json, sha256_text, write_json_atomic, write_text_atomic
from .markdown_cleaner import clean_markdown
from .source_config import SourceConfig


class CorpusBuildError(RuntimeError):
    """Raised when a validated corpus cannot be produced."""


def _percentile(sorted_values: list[int], probability: float) -> int:
    index = max(0, int(len(sorted_values) * probability + 0.999999) - 1)
    return sorted_values[index]


def _included_documents(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in manifest["documents"]
        if item["included_or_excluded"] == "included"
    ]


def build_corpus(run_dir: Path, config: SourceConfig) -> dict[str, Any]:
    manifest_path = run_dir / "source" / "document_manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(
            "缺少document_manifest.json，请先运行inspect_documents.py"
        )
    source_manifest = read_json(manifest_path)
    if source_manifest.get("status") == "blocked":
        raise CorpusBuildError("文档审计状态为blocked，拒绝构建语料")
    if source_manifest.get("commit") != config.commit:
        raise CorpusBuildError("文档manifest与冻结Commit不一致")

    repo_root = run_dir / "source" / "repository"
    corpus_dir = run_dir / "corpus"
    documents_dir = corpus_dir / "documents"
    if any(corpus_dir.iterdir()):
        raise FileExistsError(
            "corpus目录已有产物；当前命令不覆盖，请创建新的experiment_run_id"
        )
    documents_dir.mkdir(parents=True)

    cleaned_documents: list[dict[str, Any]] = []
    chunks: list[dict[str, Any]] = []
    for document in _included_documents(source_manifest):
        source_path = document["source_path"]
        raw = (repo_root / source_path).read_text(encoding="utf-8")
        cleaned, cleaning_metadata = clean_markdown(
            raw,
            source_path,
            repo_root,
            config,
        )
        relative = PurePosixPath(source_path).relative_to(config.chinese_docs_root)
        output_relative = PurePosixPath("corpus/documents") / relative
        output_path = run_dir / Path(*output_relative.parts)
        write_text_atomic(output_path, cleaned)
        document_chunks = chunk_document(cleaned, document, config.chunking)
        if not document_chunks:
            raise CorpusBuildError(f"页面未生成任何Chunk：{source_path}")
        chunks.extend(document_chunks)
        cleaned_documents.append(
            {
                "source_path": source_path,
                "cleaned_relative_path": output_relative.as_posix(),
                "cleaned_content_sha256": sha256_text(cleaned),
                "cleaning": cleaning_metadata,
                "chunk_count": len(document_chunks),
            }
        )

    chunks_path = corpus_dir / "chunks.jsonl"
    chunks_text = "".join(
        json.dumps(chunk, ensure_ascii=False, separators=(",", ":")) + "\n"
        for chunk in chunks
    )
    write_text_atomic(chunks_path, chunks_text)

    under_min = [
        chunk
        for chunk in chunks
        if chunk["token_count"] < config.chunking.target_min_tokens
    ]
    over_max = [
        chunk
        for chunk in chunks
        if chunk["token_count"] > config.chunking.target_max_tokens
    ]
    in_target = [
        chunk
        for chunk in chunks
        if (
            config.chunking.target_min_tokens
            <= chunk["token_count"]
            <= config.chunking.target_max_tokens
        )
    ]
    token_counts = sorted(chunk["token_count"] for chunk in chunks)
    corpus_hash = sha256_text(
        "\n".join(
            f"{chunk['chunk_id']}:{chunk['content_sha256']}" for chunk in chunks
        )
    )
    status = (
        "warning"
        if source_manifest.get("status") == "warning" or under_min or over_max
        else "passed"
    )
    summary = {
        "schema_version": "fastapi_corpus_v2",
        "experiment_run_id": run_dir.name,
        "status": status,
        "repository": config.repository,
        "release_tag": config.release_tag,
        "commit": config.commit,
        "chunking_strategy": config.chunking.strategy,
        "token_count_method": config.chunking.token_count_method,
        "document_count": len(cleaned_documents),
        "chunk_count": len(chunks),
        "corpus_sha256": corpus_hash,
        "chunks_jsonl_sha256": sha256_text(chunks_text),
        "group_document_counts": dict(
            sorted(
                Counter(
                    PurePosixPath(item["source_path"])
                    .relative_to(config.chinese_docs_root)
                    .parts[0]
                    for item in cleaned_documents
                ).items()
            )
        ),
        "chunks_with_code": sum(chunk["contains_code"] for chunk in chunks),
        "chunks_with_table": sum(chunk["contains_table"] for chunk in chunks),
        "chunks_with_multiple_sections": sum(
            len(chunk["section_paths"]) > 1 for chunk in chunks
        ),
        "chunks_with_overlap": sum(
            chunk["overlap_tokens"] > 0 for chunk in chunks
        ),
        "chunks_in_target_range": len(in_target),
        "target_range_ratio": round(len(in_target) / len(chunks), 6),
        "chunks_under_target_min": len(under_min),
        "chunks_over_target_max": len(over_max),
        "under_min_reason_counts": dict(
            sorted(Counter(chunk["under_min_reason"] for chunk in under_min).items())
        ),
        "over_max_reason_counts": dict(
            sorted(Counter(chunk["over_max_reason"] for chunk in over_max).items())
        ),
        "token_count_percentiles": {
            "min": token_counts[0],
            "p10": _percentile(token_counts, 0.10),
            "p25": _percentile(token_counts, 0.25),
            "median": _percentile(token_counts, 0.50),
            "p75": _percentile(token_counts, 0.75),
            "p90": _percentile(token_counts, 0.90),
            "max": token_counts[-1],
        },
        "token_count_buckets": {
            "0_49": sum(value < 50 for value in token_counts),
            "50_99": sum(50 <= value < 100 for value in token_counts),
            "100_199": sum(100 <= value < 200 for value in token_counts),
            "200_299": sum(200 <= value < 300 for value in token_counts),
            "300_399": sum(300 <= value < 400 for value in token_counts),
            "400_499": sum(400 <= value < 500 for value in token_counts),
            "500_800": sum(500 <= value <= 800 for value in token_counts),
            "801_plus": sum(value > 800 for value in token_counts),
        },
        "max_token_count": token_counts[-1],
        "min_token_count": token_counts[0],
        "documents": cleaned_documents,
    }
    write_json_atomic(corpus_dir / "corpus_manifest.json", summary)
    return summary
