from __future__ import annotations

from src.evidence_excerpt import select_evidence_excerpt


def test_excerpt_is_continuous_and_target_sized() -> None:
    content = (
        "FastAPI用于构建API。" * 20
        + "使用HTTPException返回错误。"
        + "更多解释。" * 30
    )

    result = select_evidence_excerpt(
        content,
        "如何使用HTTPException？",
        "应当raise HTTPException。",
    )

    assert 200 <= result["visible_characters"] <= 300
    assert content.strip()[
        result["start_offset"] : result["end_offset"]
    ] == result["excerpt"]


def test_excerpt_does_not_cut_a_fenced_code_block() -> None:
    code = "```python\n" + "\n".join(f"x_{i} = {i}" for i in range(40)) + "\n```"
    content = "前置说明。" * 20 + code + "后续说明。" * 20

    result = select_evidence_excerpt(
        content,
        "x_20如何定义？",
        "代码定义x_20。",
    )

    excerpt = result["excerpt"]
    if "```python" in excerpt or "x_20" in excerpt:
        assert "```python" in excerpt
        assert excerpt.count("```") == 2
