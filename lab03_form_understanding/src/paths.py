from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "configs" / "xfund_v1.0.json"
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw" / "xfund_v1.0"
LOCAL_DATA_DIR = PROJECT_ROOT / "data" / "local"
RESULTS_DIR = PROJECT_ROOT / "results"


def split_paths(split: str) -> tuple[Path, Path]:
    """Return the default annotation path and extracted image directory."""
    if split not in {"train", "val"}:
        raise ValueError(f"不支持的数据分组：{split}")
    return RAW_DATA_DIR / f"zh.{split}.json", RAW_DATA_DIR / f"zh.{split}"
