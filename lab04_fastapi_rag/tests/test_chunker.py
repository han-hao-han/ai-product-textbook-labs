from __future__ import annotations

from src.chunker import chunk_document, estimate_tokens, parse_blocks
from src.source_config import ChunkingConfig


TEST_CONFIG = ChunkingConfig(
    strategy="heading_aware_adjacent_merge_v1",
    token_count_method="deterministic_cjk_ascii_estimate_v1",
    target_min_tokens=20,
    target_max_tokens=40,
    overlap_target_tokens=8,
    overlap_min_tokens=5,
    overlap_max_tokens=10,
)


def _document() -> dict:
    return {
        "page_title": "测试页面",
        "source_path": "docs/zh/docs/tutorial/test.md",
        "commit": "a" * 40,
        "source_url": "https://example.invalid/fixed",
    }


def test_token_estimator_is_deterministic() -> None:
    text = "使用 FastAPI() 声明应用。"

    assert estimate_tokens(text) == estimate_tokens(text)
    assert estimate_tokens(text) > 0


def test_code_block_is_never_split() -> None:
    code = "\n".join(f"line_{index} = {index}" for index in range(30))
    markdown = f"# 标题\n\n````python\n{code}\n````\n"

    chunks = chunk_document(markdown, _document(), TEST_CONFIG)

    code_chunks = [chunk for chunk in chunks if chunk["contains_code"]]
    assert len(code_chunks) == 1
    assert "line_0 = 0" in code_chunks[0]["content"]
    assert "line_29 = 29" in code_chunks[0]["content"]
    assert code_chunks[0]["token_count"] > TEST_CONFIG.target_max_tokens
    assert (
        code_chunks[0]["over_max_reason"]
        == "oversized_atomic_code_block"
    )


def test_table_is_a_single_block() -> None:
    markdown = "\n".join(
        [
            "# 表格",
            "",
            "| 字段 | 说明 |",
            "|---|---|",
            "| a | 第一项 |",
            "| b | 第二项 |",
        ]
    )

    blocks = parse_blocks(markdown, "表格")

    tables = [block for block in blocks if block.kind == "table"]
    assert len(tables) == 1
    assert "| b | 第二项 |" in tables[0].text


def test_adjacent_short_sections_are_merged_with_headings() -> None:
    markdown = "\n".join(
        [
            "# 页面",
            "## 第一节",
            "第一部分。",
            "## 第二节",
            "第二部分。",
        ]
    )

    chunks = chunk_document(markdown, _document(), TEST_CONFIG)

    assert len(chunks) == 1
    assert "## 第一节" in chunks[0]["content"]
    assert "## 第二节" in chunks[0]["content"]
    assert chunks[0]["section_paths"] == [
        ["页面", "第一节"],
        ["页面", "第二节"],
    ]
    assert chunks[0]["under_min_reason"] is None
    assert (
        TEST_CONFIG.target_min_tokens
        <= chunks[0]["token_count"]
        <= TEST_CONFIG.target_max_tokens
    )


def test_overlap_is_not_copied_across_section_boundary() -> None:
    markdown = "\n".join(
        [
            "# 页面",
            "第一部分。" * 15,
            "## 第二节",
            "第二部分。" * 15,
        ]
    )

    chunks = chunk_document(markdown, _document(), TEST_CONFIG)

    assert len(chunks) >= 2
    second_section_chunk = next(
        chunk
        for chunk in chunks
        if "第二部分" in chunk["content"]
    )
    assert second_section_chunk["overlap_tokens"] == 0


def test_same_section_overlap_stays_in_configured_range() -> None:
    overlap_config = ChunkingConfig(
        strategy="heading_aware_adjacent_merge_v1",
        token_count_method="deterministic_cjk_ascii_estimate_v1",
        target_min_tokens=20,
        target_max_tokens=40,
        overlap_target_tokens=10,
        overlap_min_tokens=8,
        overlap_max_tokens=15,
    )
    markdown = "\n\n".join(
        [
            "# 页面",
            "甲。" * 10,
            "乙。" * 4,
            "丙。" * 10,
        ]
    )

    chunks = chunk_document(markdown, _document(), overlap_config)

    overlapped = [chunk for chunk in chunks if chunk["overlap_tokens"] > 0]
    assert len(overlapped) == 1
    assert (
        overlap_config.overlap_min_tokens
        <= overlapped[0]["overlap_tokens"]
        <= overlap_config.overlap_max_tokens
    )
    assert "乙。" in overlapped[0]["content"]
