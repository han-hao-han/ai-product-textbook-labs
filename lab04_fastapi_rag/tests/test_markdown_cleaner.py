from __future__ import annotations

from pathlib import Path

from src.markdown_cleaner import clean_markdown


def test_cleaner_expands_code_and_converts_links(
    frozen_repo,
) -> None:
    repo_root, config = frozen_repo
    source_path = "docs/zh/docs/tutorial/page_000.md"
    markdown = (repo_root / source_path).read_text(encoding="utf-8")

    cleaned, metadata = clean_markdown(
        markdown,
        source_path,
        repo_root,
        config,
    )

    assert "````python" in cleaned
    assert "app = FastAPI()" in cleaned
    assert "{*" not in cleaned
    assert config.commit in cleaned
    assert metadata["code_include_count"] == 1


def test_cleaner_expands_exact_approved_dependency_exception(
    frozen_repo,
) -> None:
    repo_root, config = frozen_repo
    source_path = "docs/zh/docs/how-to/configure-swagger-ui.md"
    markdown = (repo_root / source_path).read_text(encoding="utf-8")

    cleaned, metadata = clean_markdown(
        markdown,
        source_path,
        repo_root,
        config,
    )

    assert "DEFAULT_LINE_9" in cleaned
    assert "DEFAULT_LINE_24" in cleaned
    assert "DEFAULT_LINE_25" not in cleaned
    assert metadata["code_include_count"] == 1


def test_external_link_and_unsafe_html_are_removed(
    frozen_repo,
) -> None:
    repo_root, config = frozen_repo
    markdown = "\n".join(
        [
            "# 页面",
            "[外部资料](https://example.com)",
            '<img src="/x.png" alt="示意图">',
            "<script>alert('x')</script>",
        ]
    )

    cleaned, metadata = clean_markdown(
        markdown,
        "docs/zh/docs/tutorial/page_001.md",
        repo_root,
        config,
    )

    assert "https://example.com" not in cleaned
    assert "外部资料" in cleaned
    assert "[图片：示意图]" in cleaned
    assert "<script" not in cleaned
    assert metadata["unsafe_block_count"] == 1


def test_directive_wrapper_does_not_break_code_fence(
    frozen_repo,
) -> None:
    repo_root, config = frozen_repo
    markdown = "\n".join(
        [
            "# 页面",
            "/// note | 注意",
            "````python",
            "app = FastAPI()",
            "````",
            "///",
        ]
    )

    cleaned, _ = clean_markdown(
        markdown,
        "docs/zh/docs/tutorial/page_001.md",
        repo_root,
        config,
    )

    assert "> **注意**" in cleaned
    assert "\n````python\napp = FastAPI()\n````" in cleaned
