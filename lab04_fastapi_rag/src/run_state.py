from __future__ import annotations

import importlib.util
import json
import platform
import re
import secrets
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from .io_utils import read_json, write_json_atomic
from .paths import CONFIG_PATH, EMBEDDING_CONFIG_PATH, RUNS_DIR
from .source_config import SourceConfig


RUN_ID_PATTERN = re.compile(r"^fastapi_rag_\d{8}_\d{6}_[0-9a-f]{6}$")
RUN_SUBDIRECTORIES = (
    "config_snapshot",
    "source",
    "corpus",
    "model",
    "index",
    "generation",
    "calibration",
    "interactive",
    "evaluation",
    "judge",
    "checkpoints",
    "reports",
)


def make_run_id(now: datetime | None = None) -> str:
    current = now or datetime.now().astimezone()
    return f"fastapi_rag_{current:%Y%m%d_%H%M%S}_{secrets.token_hex(3)}"


def validate_run_id(run_id: str) -> str:
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError(
            "experiment_run_id格式必须为"
            "fastapi_rag_YYYYMMDD_HHMMSS_<6位小写十六进制>"
        )
    return run_id


def resolve_run_dir(run_id: str, runs_dir: Path = RUNS_DIR) -> Path:
    return runs_dir / validate_run_id(run_id)


def _probe_device(requested: str) -> dict[str, Any]:
    if requested == "cpu":
        return {
            "requested": requested,
            "frozen_device": "cpu",
            "status": "passed",
            "warning": None,
        }
    if requested != "auto" and not re.fullmatch(r"cuda:\d+", requested):
        raise ValueError("device只允许auto、cpu或cuda:<index>")

    if importlib.util.find_spec("torch") is None:
        if requested == "auto":
            return {
                "requested": requested,
                "frozen_device": "cpu",
                "status": "warning",
                "warning": "未安装torch，初始化阶段将设备冻结为CPU",
            }
        raise RuntimeError("显式请求CUDA，但当前环境未安装torch")

    import torch  # type: ignore[import-not-found]

    if requested == "auto":
        candidate = "cuda:0"
        if not torch.cuda.is_available():
            return {
                "requested": requested,
                "frozen_device": "cpu",
                "status": "warning",
                "warning": "CUDA不可用，初始化阶段将设备冻结为CPU",
            }
    else:
        candidate = requested

    index = int(candidate.split(":", maxsplit=1)[1])
    if index >= torch.cuda.device_count():
        if requested == "auto":
            return {
                "requested": requested,
                "frozen_device": "cpu",
                "status": "warning",
                "warning": f"{candidate}不存在，初始化阶段将设备冻结为CPU",
            }
        raise RuntimeError(f"显式请求的设备不存在：{candidate}")
    try:
        tensor = torch.tensor([1.0], device=candidate)
        result = float((tensor + 1).cpu().item())
    except Exception as error:
        if requested == "auto":
            return {
                "requested": requested,
                "frozen_device": "cpu",
                "status": "warning",
                "warning": f"CUDA轻量检查失败，设备冻结为CPU：{type(error).__name__}",
            }
        raise RuntimeError(f"显式CUDA轻量检查失败：{error}") from error
    if result != 2.0:
        raise RuntimeError("CUDA轻量检查结果异常")
    return {
        "requested": requested,
        "frozen_device": candidate,
        "status": "passed",
        "warning": None,
    }


def initialize_run(
    config: SourceConfig,
    run_id: str | None = None,
    device: str = "auto",
    runs_dir: Path = RUNS_DIR,
    config_path: Path = CONFIG_PATH,
) -> Path:
    selected_id = validate_run_id(run_id) if run_id else make_run_id()
    run_dir = runs_dir / selected_id
    if run_dir.exists():
        raise FileExistsError(f"运行ID已经存在，拒绝覆盖：{selected_id}")

    run_dir.mkdir(parents=True)
    try:
        for relative in RUN_SUBDIRECTORIES:
            (run_dir / relative).mkdir()
        shutil.copyfile(
            config_path,
            run_dir / "config_snapshot" / "source_config.json",
        )
        shutil.copyfile(
            EMBEDDING_CONFIG_PATH,
            run_dir / "config_snapshot" / "embedding_config.json",
        )
        device_result = _probe_device(device)
        python_is_formal_baseline = sys.version_info[:2] == (3, 10)
        precheck = {
            "schema_version": "environment_precheck_v1",
            "experiment_run_id": selected_id,
            "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "formal_python_baseline": "3.10.x",
            "formal_python_baseline_match": python_is_formal_baseline,
            "device": device_result,
        }
        manifest = {
            "schema_version": "experiment_run_v1",
            "experiment_run_id": selected_id,
            "created_at": datetime.now().astimezone().isoformat(),
            "source_schema_version": config.schema_version,
            "source_repository": config.repository,
            "source_release_tag": config.release_tag,
            "source_commit": config.commit,
            "frozen_device": device_result["frozen_device"],
            "status": "initialized",
        }
        write_json_atomic(run_dir / "environment_precheck.json", precheck)
        write_json_atomic(run_dir / "manifest.json", manifest)
    except Exception:
        shutil.rmtree(run_dir, ignore_errors=True)
        raise
    return run_dir


def load_run_manifest(run_dir: Path) -> dict[str, Any]:
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"缺少运行manifest：{manifest_path.name}")
    payload = read_json(manifest_path)
    if payload.get("experiment_run_id") != run_dir.name:
        raise ValueError("运行manifest中的experiment_run_id与目录名不一致")
    return payload


def require_compatible_run(run_dir: Path, config: SourceConfig) -> dict[str, Any]:
    manifest = load_run_manifest(run_dir)
    if manifest.get("source_commit") != config.commit:
        raise ValueError("运行目录冻结的Commit与当前配置不一致")
    if manifest.get("source_schema_version") != config.schema_version:
        raise ValueError("运行目录冻结的来源配置版本与当前配置不一致")
    return manifest
