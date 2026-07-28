from __future__ import annotations

import hashlib
import http.client
import json
import shutil
import stat
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


class DownloadError(RuntimeError):
    """Raised when an official XFUND asset cannot be prepared safely."""


ProgressCallback = Callable[[str, int, int], None]


@dataclass(frozen=True)
class AssetSpec:
    name: str
    url: str
    size: int


def load_release_config(config_path: Path) -> dict:
    with config_path.open("r", encoding="utf-8") as file:
        config = json.load(file)
    if config.get("dataset") != "XFUND" or config.get("version") != "v1.0":
        raise DownloadError("数据配置不是已审核的XFUND v1.0")
    return config


def prepare_split(
    split: str,
    *,
    config_path: Path,
    raw_dir: Path,
    timeout_seconds: float = 60.0,
    progress: ProgressCallback | None = None,
) -> dict:
    """Download, verify, and safely extract one configured XFUND split."""
    config = load_release_config(config_path)
    try:
        split_config = config["assets"][split]
    except KeyError as error:
        raise DownloadError(f"配置中不存在数据分组：{split}") from error

    raw_dir.mkdir(parents=True, exist_ok=True)
    annotation_spec = _asset_spec(split_config["annotation"])
    image_spec = _asset_spec(split_config["images"])

    annotation_record = download_asset(
        annotation_spec,
        raw_dir / annotation_spec.name,
        timeout_seconds=timeout_seconds,
        progress=progress,
    )
    image_record = download_asset(
        image_spec,
        raw_dir / image_spec.name,
        timeout_seconds=timeout_seconds,
        progress=progress,
    )

    extract_dir = raw_dir / split_config["images"]["extract_dir"]
    extraction = extract_zip_safely(raw_dir / image_spec.name, extract_dir)
    record = {
        "dataset": config["dataset"],
        "version": config["version"],
        "language": config["language"],
        "split": split,
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "annotation": annotation_record,
        "images": image_record,
        "extraction": extraction,
    }
    _update_manifest(raw_dir / "download_manifest.json", record)
    return record


def _asset_spec(payload: dict) -> AssetSpec:
    try:
        return AssetSpec(
            name=str(payload["name"]),
            url=str(payload["url"]),
            size=int(payload["size"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise DownloadError("XFUND资产配置不完整") from error


def download_asset(
    spec: AssetSpec,
    destination: Path,
    *,
    timeout_seconds: float,
    progress: ProgressCallback | None = None,
) -> dict:
    """Download one allow-listed asset using size verification and atomic replace."""
    if destination.exists():
        actual_size = destination.stat().st_size
        if actual_size != spec.size:
            raise DownloadError(
                f"本地文件大小不符：{destination.name}，"
                f"期望{spec.size}字节，实际{actual_size}字节。"
                "请人工检查后再决定是否删除或替换。"
            )
        return _file_record(spec, destination, reused=True)

    destination.parent.mkdir(parents=True, exist_ok=True)
    part_path = destination.with_name(destination.name + ".part")
    downloaded = part_path.stat().st_size if part_path.exists() else 0
    if downloaded > spec.size:
        raise DownloadError(
            f"临时文件大于官方资产：{part_path.name}，"
            f"期望不超过{spec.size}字节，实际{downloaded}字节。"
            "请人工检查后再决定是否删除。"
        )
    if downloaded == spec.size:
        part_path.replace(destination)
        return _file_record(spec, destination, reused=False)

    headers = {"User-Agent": "ai-product-textbook-lab03/1.0"}
    if downloaded:
        headers["Range"] = f"bytes={downloaded}-"
    request = urllib.request.Request(
        spec.url,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            if downloaded:
                status = getattr(response, "status", None)
                content_range = response.headers.get("Content-Range", "")
                if status != 206 or not content_range.startswith(f"bytes {downloaded}-"):
                    raise DownloadError(
                        f"服务器没有按预期响应断点续传：{spec.name}。"
                        "现有临时文件保持不变，请人工检查。"
                    )
            mode = "ab" if downloaded else "wb"
            with part_path.open(mode) as output:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
                    downloaded += len(chunk)
                    if progress is not None:
                        progress(spec.name, downloaded, spec.size)
    except DownloadError:
        raise
    except (OSError, urllib.error.URLError, http.client.HTTPException) as error:
        raise DownloadError(
            f"下载{spec.name}失败：{error}。"
            "已下载的.part内容会保留，下次运行将尝试断点续传；"
            "也可以从官方Release手工下载到data/raw/xfund_v1.0/后重新运行。"
        ) from error

    if downloaded != spec.size:
        raise DownloadError(
            f"下载大小不符：{spec.name}，期望{spec.size}字节，实际{downloaded}字节。"
            "临时文件已保留，可再次运行以尝试续传。"
        )
    part_path.replace(destination)
    return _file_record(spec, destination, reused=False)


def _file_record(spec: AssetSpec, path: Path, *, reused: bool) -> dict:
    return {
        "name": spec.name,
        "source_url": spec.url,
        "size": path.stat().st_size,
        "sha256": sha256_file(path),
        "reused_existing_file": reused,
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_zip_safely(archive_path: Path, destination: Path) -> dict:
    """Extract a ZIP after rejecting traversal paths and symbolic links."""
    if destination.exists():
        if any(destination.iterdir()):
            return {
                "directory": destination.name,
                "reused_existing_directory": True,
            }
        raise DownloadError(f"解压目录已存在但为空：{destination}")

    temporary = destination.with_name(destination.name + ".extracting")
    if temporary.exists():
        raise DownloadError(
            f"发现未完成的解压目录：{temporary}。请人工检查后再决定是否删除。"
        )

    destination_parent = destination.parent.resolve()
    temporary.mkdir(parents=True, exist_ok=False)
    try:
        with zipfile.ZipFile(archive_path) as archive:
            members = archive.infolist()
            for member in members:
                _validate_zip_member(member, temporary, destination_parent)
            archive.extractall(temporary)
        temporary.replace(destination)
    except Exception:
        resolved_temporary = temporary.resolve()
        if resolved_temporary.parent == destination_parent and temporary.exists():
            shutil.rmtree(temporary)
        raise

    return {
        "directory": destination.name,
        "reused_existing_directory": False,
        "member_count": len(members),
    }


def _validate_zip_member(
    member: zipfile.ZipInfo,
    temporary: Path,
    destination_parent: Path,
) -> None:
    member_path = Path(member.filename)
    if member_path.is_absolute() or ".." in member_path.parts:
        raise DownloadError(f"ZIP包含不安全路径：{member.filename}")
    unix_mode = member.external_attr >> 16
    if stat.S_ISLNK(unix_mode):
        raise DownloadError(f"ZIP包含不允许的符号链接：{member.filename}")

    target = (temporary / member_path).resolve()
    try:
        target.relative_to(temporary.resolve())
    except ValueError as error:
        raise DownloadError(f"ZIP成员越出解压目录：{member.filename}") from error
    if temporary.resolve().parent != destination_parent:
        raise DownloadError("临时解压目录不在预期的数据目录内")


def _update_manifest(manifest_path: Path, record: dict) -> None:
    payload = {"runs": []}
    if manifest_path.exists():
        with manifest_path.open("r", encoding="utf-8") as file:
            existing = json.load(file)
        if isinstance(existing, dict) and isinstance(existing.get("runs"), list):
            payload = existing
    payload["runs"].append(record)

    temporary = manifest_path.with_suffix(".json.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")
    temporary.replace(manifest_path)
