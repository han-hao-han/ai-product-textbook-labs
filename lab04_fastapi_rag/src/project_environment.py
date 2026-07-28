from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .paths import PROJECT_ROOT


PROJECT_DOTENV_PATH = PROJECT_ROOT / ".env"


@dataclass(frozen=True)
class CredentialEnvironment:
    dotenv_path: Path
    dotenv_exists: bool
    dotenv_loaded: bool
    credential_source: str


def load_project_environment(
    *,
    dotenv_path: Path = PROJECT_DOTENV_PATH,
    variable_name: str = "DASHSCOPE_API_KEY",
) -> CredentialEnvironment:
    """Load only the explicitly named lab04 .env without parent discovery."""
    resolved = dotenv_path.resolve()
    expected_parent = PROJECT_ROOT.resolve()
    if dotenv_path == PROJECT_DOTENV_PATH and resolved.parent != expected_parent:
        raise ValueError("项目.env路径必须位于lab04_fastapi_rag根目录")
    existed_before = bool(os.environ.get(variable_name, "").strip())
    dotenv_exists = resolved.is_file()
    dotenv_loaded = False
    if dotenv_exists:
        from dotenv import load_dotenv

        dotenv_loaded = bool(
            load_dotenv(
                dotenv_path=resolved,
                override=False,
                verbose=False,
            )
        )
    exists_after = bool(os.environ.get(variable_name, "").strip())
    if existed_before:
        source = "process_environment"
    elif exists_after and dotenv_exists:
        source = "lab04_project_dotenv"
    else:
        source = "missing"
    return CredentialEnvironment(
        dotenv_path=resolved,
        dotenv_exists=dotenv_exists,
        dotenv_loaded=dotenv_loaded,
        credential_source=source,
    )
