from __future__ import annotations

import http.client
import io
import zipfile
from email.message import Message
from pathlib import Path

import pytest

from src.downloader import (
    DownloadError,
    _download_to_path,
    _record_download_failure,
    inspect_zip_safety,
)
from src.io_utils import read_json
from src.source_config import load_source_config


def test_safe_zip_is_accepted(tmp_path: Path) -> None:
    archive_path = tmp_path / "safe.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("fastapi-fixed/LICENSE", "The MIT License (MIT)")

    members = inspect_zip_safety(archive_path)

    assert [item.filename for item in members] == ["fastapi-fixed/LICENSE"]


def test_zip_path_traversal_is_rejected(tmp_path: Path) -> None:
    archive_path = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("../outside.txt", "unsafe")

    with pytest.raises(DownloadError, match="不安全路径"):
        inspect_zip_safety(archive_path)


def test_non_zip_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "not-a-zip"
    path.write_text("not a zip", encoding="utf-8")

    with pytest.raises(DownloadError, match="有效ZIP"):
        inspect_zip_safety(path)


def test_download_failure_is_recorded_without_absolute_path(tmp_path: Path) -> None:
    run_dir = tmp_path / "fastapi_rag_20260728_010203_abcdef"
    run_dir.mkdir()

    failure_path = _record_download_failure(
        run_dir,
        load_source_config(),
        DownloadError("固定来源检查失败"),
    )
    payload = read_json(failure_path)

    assert payload["error_stage"] == "download_or_source_verification"
    assert payload["error_type"] == "DownloadError"
    assert payload["download_attempts"] == []
    assert str(tmp_path) not in failure_path.read_text(encoding="utf-8")


def test_incomplete_read_is_retried_from_the_beginning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = b"complete fixed archive"
    calls = 0

    class FakeResponse:
        status = 200

        def __init__(self, *, fail: bool) -> None:
            self.fail = fail
            self.stream = io.BytesIO(payload)
            self.headers = Message()
            self.headers["Content-Type"] = "application/zip"

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def read(self, size: int = -1) -> bytes:
            if self.fail:
                self.fail = False
                raise http.client.IncompleteRead(b"partial", 10)
            return self.stream.read(size)

    def fake_urlopen(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return FakeResponse(fail=calls == 1)

    monkeypatch.setattr(
        "src.downloader.urllib.request.urlopen",
        fake_urlopen,
    )
    monkeypatch.setattr("src.downloader.time.sleep", lambda _seconds: None)
    destination = tmp_path / "archive.zip"

    metadata = _download_to_path("https://example.test/fixed.zip", destination)

    assert calls == 2
    assert destination.read_bytes() == payload
    assert metadata["attempt_count"] == 2
    assert metadata["retry_errors"][0]["error_type"] == "IncompleteRead"
