from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.document_manifest import (  # noqa: E402
    DocumentAuditError,
    build_document_manifest,
)
from src.run_state import require_compatible_run, resolve_run_dir  # noqa: E402
from src.source_config import load_source_config  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="检查冻结中文文档范围、代码依赖和内部链接。"
    )
    parser.add_argument("--experiment-run-id", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print("[检查点1/步骤2] 检查中文文档范围和依赖")
    try:
        config = load_source_config()
        run_dir = resolve_run_dir(args.experiment_run_id)
        require_compatible_run(run_dir, config)
        manifest = build_document_manifest(run_dir, config)
    except (
        DocumentAuditError,
        FileNotFoundError,
        OSError,
        RuntimeError,
        UnicodeError,
        ValueError,
    ) as error:
        print(f"文档检查失败：{type(error).__name__}: {error}", file=sys.stderr)
        return 1

    print(f"状态：{manifest['status']}")
    print(f"候选Markdown：{manifest['candidate_markdown_files']}")
    print(f"纳入Markdown：{manifest['included_markdown_files']}")
    print(f"排除Markdown：{manifest['excluded_markdown_files']}")
    print(f"分组：{manifest['included_group_counts']}")
    print(f"代码引用：{manifest['code_include_references']}")
    print(f"唯一代码依赖：{manifest['unique_code_dependencies']}")
    print(f"依赖范围：{manifest['code_dependency_scope_counts']}")
    print(f"缺失代码依赖：{len(manifest['missing_code_dependencies'])}")
    print(f"内部链接状态：{manifest['link_status_counts']}")
    print(f"缺失内部链接：{len(manifest['missing_internal_links'])}")
    print("\n已排除页面：")
    for item in config.excluded_pages:
        print(f"- {item['source_path']}：{item['excluded_reason']}")
    print("\n已批准代码依赖例外：")
    for item in manifest["approved_dependency_exceptions"]:
        start, end = item["line_selection"]
        print(
            f"- {item['source_path']} -> {item['dependency_path']} "
            f"ln[{start}:{end}]："
            f"{item['actual_occurrences']}/{item['expected_occurrences']}"
        )
    print("\n代表页面：")
    for group in config.included_groups:
        sample = next(
            item
            for item in manifest["documents"]
            if item["included_or_excluded"] == "included"
            and item["document_group"] == group
        )
        print(f"- {group}：{sample['page_title']}（{sample['source_path']}）")
    print("\n生成文件：source/document_manifest.json")
    if manifest["status"] == "blocked":
        print("文档检查被阻断，不得继续构建语料。", file=sys.stderr)
        return 1
    if manifest["status"] == "warning":
        print("警告：存在无法解析的内部链接；详情见document_manifest.json。")
    print("下一步：")
    print(
        "python scripts/build_corpus.py "
        f"--experiment-run-id {run_dir.name}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
