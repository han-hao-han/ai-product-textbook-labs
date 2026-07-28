from __future__ import annotations

from pathlib import Path

import pytest

from src.document_manifest import (
    DocumentAuditError,
    build_document_manifest,
    resolve_code_include_path,
)


def test_manifest_enforces_frozen_scope(
    tmp_path: Path,
    frozen_repo,
) -> None:
    repo_root, config = frozen_repo
    run_dir = tmp_path / "run"
    source_dir = run_dir / "source"
    source_dir.mkdir(parents=True)
    repo_root.rename(source_dir / "repository")

    manifest = build_document_manifest(run_dir, config)

    assert manifest["status"] == "passed"
    assert manifest["candidate_markdown_files"] == 105
    assert manifest["included_markdown_files"] == 102
    assert manifest["excluded_markdown_files"] == 3
    assert manifest["code_include_references"] == 2
    assert manifest["unique_code_dependencies"] == 2
    assert manifest["code_dependency_scope_counts"] == {
        "approved_exception": 1,
        "code_source_root": 1,
    }
    assert manifest["approved_dependency_exceptions"][0][
        "actual_occurrences"
    ] == 1
    assert manifest["missing_code_dependencies"] == []
    assert manifest["link_status_counts"]["internal_in_corpus"] == 1


def test_code_include_uses_fastapi_language_build_root(frozen_repo) -> None:
    _, config = frozen_repo

    tutorial_resolved = resolve_code_include_path(
        "docs/zh/docs/tutorial/body.md",
        "../../docs_src/body/tutorial001_py310.py",
        config,
    )
    nested_resolved = resolve_code_include_path(
        "docs/zh/docs/advanced/security/http-basic-auth.md",
        "../../docs_src/security/tutorial006_an_py310.py",
        config,
    )

    assert tutorial_resolved == "docs_src/body/tutorial001_py310.py"
    assert nested_resolved == "docs_src/security/tutorial006_an_py310.py"


def test_unapproved_fastapi_source_dependency_is_rejected(
    tmp_path: Path,
    frozen_repo,
) -> None:
    repo_root, config = frozen_repo
    unapproved_page = (
        repo_root / config.chinese_docs_root / "tutorial" / "page_001.md"
    )
    unapproved_page.write_text(
        "\n".join(
            [
                "# 未批准引用",
                "",
                "{* ../../fastapi/openapi/docs.py ln[9:24] *}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    run_dir = tmp_path / "run"
    source_dir = run_dir / "source"
    source_dir.mkdir(parents=True)
    repo_root.rename(source_dir / "repository")

    with pytest.raises(DocumentAuditError, match="不在冻结依赖范围内"):
        build_document_manifest(run_dir, config)
