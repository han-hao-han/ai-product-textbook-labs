from __future__ import annotations

import os

from src.project_environment import load_project_environment


def test_loads_only_explicit_dotenv_path(tmp_path, monkeypatch) -> None:
    dotenv = tmp_path / "lab04.env"
    dotenv.write_text(
        "DASHSCOPE_API_KEY=from-project-dotenv\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)

    result = load_project_environment(dotenv_path=dotenv)

    assert os.environ["DASHSCOPE_API_KEY"] == "from-project-dotenv"
    assert result.credential_source == "lab04_project_dotenv"
    assert result.dotenv_exists is True


def test_process_environment_has_priority_over_dotenv(
    tmp_path,
    monkeypatch,
) -> None:
    dotenv = tmp_path / "lab04.env"
    dotenv.write_text(
        "DASHSCOPE_API_KEY=from-file\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DASHSCOPE_API_KEY", "from-process")

    result = load_project_environment(dotenv_path=dotenv)

    assert os.environ["DASHSCOPE_API_KEY"] == "from-process"
    assert result.credential_source == "process_environment"


def test_missing_explicit_dotenv_does_not_search_parent(
    tmp_path,
    monkeypatch,
) -> None:
    (tmp_path / ".env").write_text(
        "DASHSCOPE_API_KEY=parent-secret\n",
        encoding="utf-8",
    )
    nested = tmp_path / "nested"
    nested.mkdir()
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)

    result = load_project_environment(
        dotenv_path=nested / ".env",
    )

    assert "DASHSCOPE_API_KEY" not in os.environ
    assert result.credential_source == "missing"
