from __future__ import annotations

import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def frozen_repo(tmp_path: Path):
    from src.source_config import load_source_config

    config = load_source_config()
    repo_root = tmp_path / "repository"
    docs_root = repo_root / config.chinese_docs_root
    code_root = repo_root / config.code_source_root
    code_root.mkdir(parents=True)
    (repo_root / "LICENSE").write_text(
        "The MIT License (MIT)\n", encoding="utf-8"
    )

    exclusion_map = config.excluded_path_map
    serial = 0
    for group, included_count in config.included_groups.items():
        group_dir = docs_root / group
        group_dir.mkdir(parents=True)
        for index in range(included_count):
            serial += 1
            filename = (
                "configure-swagger-ui.md"
                if group == "how-to" and index == 0
                else f"page_{index:03d}.md"
            )
            path = group_dir / filename
            path.write_text(
                f"# {group} 页面 {index}\n\n这是固定测试内容{serial}。\n",
                encoding="utf-8",
            )

    for source_path in exclusion_map:
        path = repo_root / source_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# 排除页面\n\n不进入语料。\n", encoding="utf-8")

    sample_path = docs_root / "tutorial" / "page_000.md"
    sample_path.write_text(
        "\n".join(
            [
                "# 请求体",
                "",
                "参见[高级页](../advanced/page_000.md)。",
                "",
                "{* ../../docs_src/body/example.py hl[2] *}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    code_path = code_root / "body" / "example.py"
    code_path.parent.mkdir(parents=True)
    code_path.write_text(
        "from fastapi import FastAPI\n\napp = FastAPI()\n",
        encoding="utf-8",
    )
    exception = config.code_dependency_exceptions[0]
    exception_page = repo_root / exception.source_path
    exception_page.write_text(
        "\n".join(
            [
                "# 配置Swagger UI",
                "",
                "以下是默认配置参数。",
                "",
                "{* ../../fastapi/openapi/docs.py ln[9:24] hl[18:24] *}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    exception_code = repo_root / exception.dependency_path
    exception_code.parent.mkdir(parents=True)
    exception_code.write_text(
        "\n".join(f"DEFAULT_LINE_{line}" for line in range(1, 31)) + "\n",
        encoding="utf-8",
    )
    return repo_root, config
