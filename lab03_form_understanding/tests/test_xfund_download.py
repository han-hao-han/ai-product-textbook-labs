from __future__ import annotations

import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from src.xfund_download import AssetSpec, DownloadError, download_asset, extract_zip_safely


class XfundDownloadTests(unittest.TestCase):
    def test_reuses_existing_asset_only_when_size_matches(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "asset.json"
            destination.write_bytes(b"1234")
            spec = AssetSpec(
                name="asset.json",
                url="https://example.invalid/asset.json",
                size=4,
            )

            record = download_asset(spec, destination, timeout_seconds=1)

        self.assertTrue(record["reused_existing_file"])
        self.assertEqual(record["size"], 4)

    def test_resumes_an_existing_partial_download(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "asset.json"
            part_path = destination.with_name("asset.json.part")
            part_path.write_bytes(b"12")
            spec = AssetSpec(
                name="asset.json",
                url="https://example.invalid/asset.json",
                size=4,
            )
            response = io.BytesIO(b"34")
            response.status = 206
            response.headers = {"Content-Range": "bytes 2-3/4"}

            with patch("src.xfund_download.urllib.request.urlopen", return_value=response):
                record = download_asset(spec, destination, timeout_seconds=1)

            self.assertEqual(destination.read_bytes(), b"1234")
            self.assertFalse(part_path.exists())
            self.assertFalse(record["reused_existing_file"])

    def test_promotes_a_complete_partial_file_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "asset.json"
            part_path = destination.with_name("asset.json.part")
            part_path.write_bytes(b"1234")
            spec = AssetSpec(
                name="asset.json",
                url="https://example.invalid/asset.json",
                size=4,
            )

            record = download_asset(spec, destination, timeout_seconds=1)

            self.assertEqual(destination.read_bytes(), b"1234")
            self.assertFalse(part_path.exists())
            self.assertFalse(record["reused_existing_file"])

    def test_extracts_safe_zip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive_path = root / "safe.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("images/a.txt", "ok")

            record = extract_zip_safely(archive_path, root / "extracted")

            self.assertEqual((root / "extracted" / "images" / "a.txt").read_text(), "ok")
            self.assertEqual(record["member_count"], 1)

    def test_rejects_zip_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive_path = root / "unsafe.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("../outside.txt", "not allowed")

            with self.assertRaisesRegex(DownloadError, "不安全路径"):
                extract_zip_safely(archive_path, root / "extracted")

            self.assertFalse((root / "outside.txt").exists())
            self.assertFalse((root / "extracted.extracting").exists())


if __name__ == "__main__":
    unittest.main()
