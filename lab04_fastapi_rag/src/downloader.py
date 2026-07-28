from __future__ import annotations

import http.client
import json
import os
import shutil
import stat
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from .io_utils import git_blob_sha1, sha256_file, write_json_atomic
from .source_config import SourceConfig


USER_AGENT = "ai-product-textbook-fastapi-rag/1.0"
DOWNLOAD_TIMEOUT_SECONDS = 120
DOWNLOAD_MAX_ATTEMPTS = 3
DOWNLOAD_RETRY_DELAYS_SECONDS = (1, 3)


class DownloadError(RuntimeError):
    """Raised when the fixed source archive cannot be safely prepared."""

    def __init__(
        self,
        message: str,
        *,
        attempt_errors: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.attempt_errors = tuple(attempt_errors or [])


def _record_download_failure(
    run_dir: Path,
    config: SourceConfig,
    error: Exception,
) -> Path:
    failures_dir = run_dir / "source" / "download_failures"
    failures_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(failures_dir.glob("failure_*.json"))
    failure_path = failures_dir / f"failure_{len(existing) + 1:03d}.json"
    write_json_atomic(
        failure_path,
        {
            "schema_version": "fastapi_download_failure_v2",
            "experiment_run_id": run_dir.name,
            "failed_at": datetime.now().astimezone().isoformat(),
            "error_stage": "download_or_source_verification",
            "error_type": type(error).__name__,
            "error_message": str(error),
            "download_attempts": list(
                getattr(error, "attempt_errors", ())
            ),
            "repository": config.repository,
            "release_tag": config.release_tag,
            "commit": config.commit,
        },
    )
    return failure_path


def _safe_zip_members(archive: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    members = archive.infolist()
    if not members:
        raise DownloadError("官方ZIP为空")
    for info in members:
        path = PurePosixPath(info.filename)
        if path.is_absolute() or ".." in path.parts:
            raise DownloadError(f"ZIP包含不安全路径：{info.filename}")
        unix_mode = info.external_attr >> 16
        if unix_mode and stat.S_ISLNK(unix_mode):
            raise DownloadError(f"ZIP包含符号链接，拒绝解压：{info.filename}")
    return members


def inspect_zip_safety(path: Path) -> list[zipfile.ZipInfo]:
    if not zipfile.is_zipfile(path):
        raise DownloadError("下载内容不是有效ZIP")
    with zipfile.ZipFile(path) as archive:
        return _safe_zip_members(archive)


def _download_once(url: str, destination: Path) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/zip, application/octet-stream",
        },
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=DOWNLOAD_TIMEOUT_SECONDS,
        ) as response:
            status = getattr(response, "status", None)
            if status != 200:
                raise DownloadError(f"官方ZIP请求返回HTTP {status}")
            content_type = response.headers.get_content_type()
            if content_type not in {
                "application/zip",
                "application/octet-stream",
                "application/x-zip-compressed",
            }:
                raise DownloadError(f"官方ZIP返回了异常Content-Type：{content_type}")
            with destination.open("wb") as output:
                shutil.copyfileobj(response, output, length=1024 * 1024)
            return {
                "http_status": status,
                "content_type": content_type,
                "content_length_header": response.headers.get("Content-Length"),
                "etag": response.headers.get("ETag"),
            }
    except urllib.error.HTTPError as error:
        raise DownloadError(f"官方ZIP请求失败：HTTP {error.code}") from error


def _download_to_path(url: str, destination: Path) -> dict[str, Any]:
    attempt_errors: list[dict[str, Any]] = []
    for attempt in range(1, DOWNLOAD_MAX_ATTEMPTS + 1):
        try:
            metadata = _download_once(url, destination)
            return {
                **metadata,
                "attempt_count": attempt,
                "retry_errors": attempt_errors,
            }
        except DownloadError:
            raise
        except (
            http.client.HTTPException,
            urllib.error.URLError,
            TimeoutError,
            ConnectionError,
        ) as error:
            destination.unlink(missing_ok=True)
            attempt_errors.append(
                {
                    "attempt": attempt,
                    "error_type": type(error).__name__,
                    "error_message": str(error),
                }
            )
            if attempt >= DOWNLOAD_MAX_ATTEMPTS:
                raise DownloadError(
                    "官方ZIP传输连续失败"
                    f"{DOWNLOAD_MAX_ATTEMPTS}次；"
                    f"最后错误为{type(error).__name__}: {error}",
                    attempt_errors=attempt_errors,
                ) from error
            time.sleep(DOWNLOAD_RETRY_DELAYS_SECONDS[attempt - 1])
    raise AssertionError("下载重试循环未返回结果")


def _single_archive_root(members: list[zipfile.ZipInfo]) -> str:
    roots = {
        PurePosixPath(info.filename).parts[0]
        for info in members
        if PurePosixPath(info.filename).parts
    }
    if len(roots) != 1:
        raise DownloadError(f"ZIP顶层目录数量异常：{len(roots)}")
    return next(iter(roots))


def _verify_extracted_repository(repo_root: Path, config: SourceConfig) -> dict[str, Any]:
    license_path = repo_root / config.license_path
    if not license_path.is_file():
        raise DownloadError(f"固定Commit缺少许可证：{config.license_path}")
    license_content = license_path.read_bytes()
    actual_blob_sha1 = git_blob_sha1(license_content)
    if actual_blob_sha1 != config.license_git_blob_sha1:
        raise DownloadError(
            "LICENSE Git blob SHA-1不匹配："
            f"expected={config.license_git_blob_sha1}, actual={actual_blob_sha1}"
        )
    license_text = license_content.decode("utf-8")
    if "The MIT License (MIT)" not in license_text:
        raise DownloadError("LICENSE内容不是预期的MIT许可证")

    chinese_root = repo_root / config.chinese_docs_root
    code_root = repo_root / config.code_source_root
    if not chinese_root.is_dir():
        raise DownloadError(f"缺少中文文档根目录：{config.chinese_docs_root}")
    if not code_root.is_dir():
        raise DownloadError(f"缺少代码依赖根目录：{config.code_source_root}")
    for group in config.included_groups:
        group_dir = chinese_root / group
        if not group_dir.is_dir():
            raise DownloadError(f"缺少中文文档分组：{group}")
    for source_path in config.excluded_path_map:
        if not (repo_root / source_path).is_file():
            raise DownloadError(f"冻结排除页面不存在：{source_path}")
    verified_exceptions: list[dict[str, Any]] = []
    for exception in config.code_dependency_exceptions:
        if not (repo_root / exception.source_path).is_file():
            raise DownloadError(
                f"代码依赖例外所属页面不存在：{exception.source_path}"
            )
        if not (repo_root / exception.dependency_path).is_file():
            raise DownloadError(
                f"代码依赖例外目标不存在：{exception.dependency_path}"
            )
        verified_exceptions.append(
            {
                "source_path": exception.source_path,
                "dependency_path": exception.dependency_path,
                "line_selection": exception.line_selection,
                "expected_occurrences": exception.expected_occurrences,
            }
        )
    return {
        "license_path": config.license_path,
        "license_git_blob_sha1": actual_blob_sha1,
        "license_name": "MIT",
        "chinese_docs_root": config.chinese_docs_root,
        "code_source_root": config.code_source_root,
        "code_dependency_exceptions": verified_exceptions,
    }


def download_and_extract(
    run_dir: Path,
    config: SourceConfig,
) -> dict[str, Any]:
    source_dir = run_dir / "source"
    archive_path = source_dir / "fastapi_source.zip"
    repository_dir = source_dir / "repository"
    metadata_path = source_dir / "download.json"

    if metadata_path.exists() or repository_dir.exists() or archive_path.exists():
        raise FileExistsError(
            "source目录已有下载产物；当前命令不覆盖，请创建新的experiment_run_id"
        )

    source_dir.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".fastapi_source.",
        suffix=".zip",
        dir=source_dir,
    )
    os.close(descriptor)
    temporary_archive = Path(temporary_name)
    temporary_extract = Path(
        tempfile.mkdtemp(prefix=".extract.", dir=source_dir)
    )
    try:
        response_metadata = _download_to_path(config.archive_url, temporary_archive)
        members = inspect_zip_safety(temporary_archive)
        archive_root = _single_archive_root(members)
        with zipfile.ZipFile(temporary_archive) as archive:
            archive.extractall(temporary_extract, members=members)

        extracted_root = temporary_extract / archive_root
        verification = _verify_extracted_repository(extracted_root, config)
        archive_sha256 = sha256_file(temporary_archive)
        archive_bytes = temporary_archive.stat().st_size

        os.replace(temporary_archive, archive_path)
        shutil.move(str(extracted_root), str(repository_dir))
        metadata = {
            "schema_version": "fastapi_download_v1",
            "experiment_run_id": run_dir.name,
            "downloaded_at": datetime.now().astimezone().isoformat(),
            "repository": config.repository,
            "release_tag": config.release_tag,
            "commit": config.commit,
            "archive_url": config.archive_url,
            "archive_relative_path": "source/fastapi_source.zip",
            "repository_relative_path": "source/repository",
            "archive_sha256": archive_sha256,
            "archive_bytes": archive_bytes,
            "zip_member_count": len(members),
            "response": response_metadata,
            "verification": verification,
        }
        write_json_atomic(metadata_path, metadata)
        return metadata
    except Exception as error:
        temporary_archive.unlink(missing_ok=True)
        if repository_dir.exists():
            shutil.rmtree(repository_dir, ignore_errors=True)
        if archive_path.exists():
            archive_path.unlink(missing_ok=True)
        if metadata_path.exists():
            metadata_path.unlink(missing_ok=True)
        try:
            _record_download_failure(run_dir, config, error)
        except OSError:
            # Preserve the original download or verification failure.
            pass
        raise
    finally:
        shutil.rmtree(temporary_extract, ignore_errors=True)
