from __future__ import annotations

import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from .embedding_config import EmbeddingConfig
from .io_utils import read_json, write_json_atomic, write_text_atomic


def write_checkpoint2_report(
    run_dir: Path,
    config: EmbeddingConfig,
    retrieval_result: dict[str, Any],
) -> tuple[Path, Path, Path]:
    model_record = read_json(run_dir / "model" / "embedding_model.json")
    index_manifest = read_json(
        run_dir / "index" / "current" / "index_manifest.json"
    )
    corpus_manifest = read_json(run_dir / "corpus" / "corpus_manifest.json")
    checkpoint_dir = run_dir / "checkpoints" / "checkpoint_2"
    if checkpoint_dir.exists():
        raise FileExistsError("检查点2报告已经存在，拒绝覆盖")
    status = "warning" if corpus_manifest.get("status") == "warning" else "passed"
    payload = {
        "schema_version": "checkpoint_2_report_v1",
        "checkpoint": "checkpoint_2",
        "title": "模型、索引与Top 5",
        "experiment_run_id": run_dir.name,
        "created_at": datetime.now().astimezone().isoformat(),
        "status": status,
        "embedding_model": model_record,
        "index": index_manifest,
        "retrieval_demo": retrieval_result,
        "model_calls": {
            "local_embedding": True,
            "online_generation": False,
            "codex_judge": False,
        },
    }
    hit_lines: list[str] = []
    for hit in retrieval_result["hits"]:
        section = " > ".join(hit["section_path"])
        hit_lines.extend(
            [
                f"### Top {hit['rank']}：{hit['page_title']}",
                "",
                f"- Score：{hit['score']:.6f}",
                f"- Chunk ID：`{hit['chunk_id']}`",
                f"- 来源：`{hit['source_path']}`",
                f"- 章节：{section}",
                f"- Chunk序号：{hit['chunk_index']}",
                f"- 含代码：{hit['contains_code']}",
                "",
                hit["content"],
                "",
            ]
        )
    markdown = "\n".join(
        [
            "# 检查点2报告：模型、索引与Top 5",
            "",
            "## 状态",
            "",
            f"```text\n{status}\n```",
            "",
            "## 本地Embedding模型",
            "",
            f"- 模型：`{config.model_id}`",
            f"- Revision：`{config.revision}`",
            f"- License：{config.license}",
            f"- 设备：{model_record['device']}",
            f"- 维度：{model_record['dimension']}",
            f"- 池化：{model_record['pooling']}",
            f"- 归一化：{model_record['normalization']}",
            f"- 查询任务指令：{config.query_instruction}",
            "",
            "## NumPy索引",
            "",
            f"- 矩阵形状：{index_manifest['matrix_shape']}",
            f"- dtype：{index_manifest['matrix_dtype']}",
            f"- Chunk顺序哈希：`{index_manifest['chunk_order_sha256']}`",
            f"- 索引哈希：`{index_manifest['embeddings_sha256']}`",
            f"- 最大输入Token：{index_manifest['embedding_diagnostics']['max_input_tokens']}",
            f"- 截断输入：{index_manifest['embedding_diagnostics']['truncated_input_count']}",
            f"- 构建耗时：{index_manifest['elapsed_seconds']}秒",
            "",
            "## 固定问题",
            "",
            retrieval_result["query"],
            "",
            "## 精确余弦Top 5",
            "",
            *hit_lines,
            "## 读者应该观察什么",
            "",
            "- 文档与查询使用同一模型和Revision，但只有查询带任务指令；",
            "- 向量经过L2归一化后，点积等于余弦相似度；",
            "- Top 5来自NumPy全量精确排序，不是近似向量数据库；",
            "- 分数和排名由程序计算，模型不评价自己的检索质量；",
            "- 本检查点尚未冻结门控阈值，也未调用在线生成模型。",
            "",
            "## 真实性声明",
            "",
            "本检查点真实调用了本地Embedding模型；未调用在线生成模型或"
            "Codex Judge，也未产生RAG最终答案。",
            "",
        ]
    )
    staging_dir = Path(
        tempfile.mkdtemp(
            prefix=".checkpoint_2.",
            dir=run_dir / "checkpoints",
        )
    )
    report_json = staging_dir / "report.json"
    report_md = staging_dir / "report.md"
    demo_json = staging_dir / "demo_retrieval.json"
    try:
        write_json_atomic(demo_json, retrieval_result)
        write_json_atomic(report_json, payload)
        write_text_atomic(report_md, markdown)
        os.replace(staging_dir, checkpoint_dir)
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise
    return (
        checkpoint_dir / "report.md",
        checkpoint_dir / "report.json",
        checkpoint_dir / "demo_retrieval.json",
    )
