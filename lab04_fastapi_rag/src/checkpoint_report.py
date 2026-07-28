from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from .io_utils import write_json_atomic, write_text_atomic
from .source_config import SourceConfig


VALID_CHECKPOINT_STATUSES = {"passed", "warning", "blocked", "not_run"}


def write_checkpoint1_report(
    run_dir: Path,
    config: SourceConfig,
    status: str,
    source_manifest: dict[str, Any] | None = None,
    corpus_manifest: dict[str, Any] | None = None,
    errors: list[str] | None = None,
) -> tuple[Path, Path]:
    if status not in VALID_CHECKPOINT_STATUSES:
        raise ValueError(f"无效检查点状态：{status}")
    error_list = list(errors or [])
    checkpoint_dir = run_dir / "checkpoints" / "checkpoint_1"
    report_json = checkpoint_dir / "report.json"
    report_md = checkpoint_dir / "report.md"

    payload = {
        "schema_version": "checkpoint_1_report_v3",
        "checkpoint": "checkpoint_1",
        "title": "文档、清洗与Chunk",
        "experiment_run_id": run_dir.name,
        "created_at": datetime.now().astimezone().isoformat(),
        "status": status,
        "source": {
            "repository": config.repository,
            "release_tag": config.release_tag,
            "commit": config.commit,
            "expected_included_pages": config.expected_included_pages,
            "excluded_pages": list(config.excluded_pages),
            "code_dependency_exceptions": [
                {
                    "source_path": item.source_path,
                    "dependency_path": item.dependency_path,
                    "line_selection": item.line_selection,
                    "expected_occurrences": item.expected_occurrences,
                    "reason": item.reason,
                }
                for item in config.code_dependency_exceptions
            ],
        },
        "document_audit": source_manifest,
        "corpus": corpus_manifest,
        "errors": error_list,
        "model_calls": {
            "embedding": False,
            "generation": False,
            "codex_judge": False,
        },
    }
    write_json_atomic(report_json, payload)

    document_lines = [
        f"- 候选Markdown：{source_manifest.get('candidate_markdown_files', '未运行')}",
        f"- 纳入Markdown：{source_manifest.get('included_markdown_files', '未运行')}",
        f"- 排除Markdown：{source_manifest.get('excluded_markdown_files', '未运行')}",
        f"- 代码引用：{source_manifest.get('code_include_references', '未运行')}",
        f"- 唯一代码依赖：{source_manifest.get('unique_code_dependencies', '未运行')}",
        f"- 依赖范围：{source_manifest.get('code_dependency_scope_counts', '未运行')}",
        f"- 已批准依赖例外：{len(source_manifest.get('approved_dependency_exceptions', []))}",
        f"- 缺失代码依赖：{len(source_manifest.get('missing_code_dependencies', []))}",
        f"- 缺失内部链接：{len(source_manifest.get('missing_internal_links', []))}",
    ] if source_manifest else ["- 未运行文档审计"]

    corpus_lines = [
        f"- 清洗文档：{corpus_manifest.get('document_count', '未运行')}",
        f"- Chunk：{corpus_manifest.get('chunk_count', '未运行')}",
        f"- Chunk策略：{corpus_manifest.get('chunking_strategy', '未运行')}",
        f"- 含代码Chunk：{corpus_manifest.get('chunks_with_code', '未运行')}",
        f"- 含表格Chunk：{corpus_manifest.get('chunks_with_table', '未运行')}",
        f"- 合并多个相关小节的Chunk：{corpus_manifest.get('chunks_with_multiple_sections', '未运行')}",
        f"- 含Overlap的Chunk：{corpus_manifest.get('chunks_with_overlap', '未运行')}",
        f"- 位于500～800目标区间：{corpus_manifest.get('chunks_in_target_range', '未运行')}",
        f"- 目标区间占比：{corpus_manifest.get('target_range_ratio', '未运行')}",
        f"- 低于目标下限：{corpus_manifest.get('chunks_under_target_min', '未运行')}",
        f"- 低于下限原因：{corpus_manifest.get('under_min_reason_counts', '未运行')}",
        f"- 超过目标上限：{corpus_manifest.get('chunks_over_target_max', '未运行')}",
        f"- 超过上限原因：{corpus_manifest.get('over_max_reason_counts', '未运行')}",
        f"- 长度分位数：{corpus_manifest.get('token_count_percentiles', '未运行')}",
        f"- 长度区间分布：{corpus_manifest.get('token_count_buckets', '未运行')}",
        f"- Token计数方法：{corpus_manifest.get('token_count_method', '未运行')}",
        f"- 语料哈希：{corpus_manifest.get('corpus_sha256', '未运行')}",
    ] if corpus_manifest else ["- 未运行语料构建"]

    error_lines = [f"- {error}" for error in error_list] or ["- 无"]
    markdown = "\n".join(
        [
            "# 检查点1报告：文档、清洗与Chunk",
            "",
            "## 状态",
            "",
            f"```text\n{status}\n```",
            "",
            "## 固定来源",
            "",
            f"- Repository：{config.repository}",
            f"- Release：{config.release_tag}",
            f"- Commit：{config.commit}",
            "- License：MIT",
            "",
            "## 文档审计",
            "",
            *document_lines,
            "",
            "## 清洗与Chunk",
            "",
            *corpus_lines,
            "",
            "## 错误",
            "",
            *error_lines,
            "",
            "## 读者应该观察什么",
            "",
            "- 纳入页面是否严格为H1确认的102页；",
            "- 三个外围页面是否被明确排除；",
            "- docs_src代码依赖是否全部存在并展开；",
            "- 唯一批准的fastapi/openapi/docs.py例外是否精确出现一次；",
            "- 代码块和表格是否保持完整；",
            "- 相邻相关短小节是否合并，正文中是否保留必要标题；",
            "- 每个Chunk是否带有Commit、源路径、全部章节路径和哈希；",
            "- Overlap是否只来自同一章节；",
            "- 过短或超长Chunk是否带有明确原因。",
            "",
            "## 真实性声明",
            "",
            "本检查点未调用Embedding模型、在线生成模型或Codex Judge，"
            "也未产生真实检索、回答或评价结果。",
            "",
        ]
    )
    write_text_atomic(report_md, markdown)
    return report_md, report_json
