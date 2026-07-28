from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.xfund_loader import DataFormatError, load_xfund_documents, resolve_image_path


class XfundLoaderTests(unittest.TestCase):
    def test_loads_minimum_valid_document(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            annotation_path = Path(directory) / "mock.json"
            annotation_path.write_text(
                json.dumps({"documents": [_document("doc-1", "doc-1.png")]}),
                encoding="utf-8",
            )

            documents = load_xfund_documents(annotation_path)

        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0]["id"], "doc-1")

    def test_rejects_duplicate_document_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            annotation_path = Path(directory) / "mock.json"
            annotation_path.write_text(
                json.dumps(
                    {"documents": [_document("same", "1.png"), _document("same", "2.png")]}
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(DataFormatError, "重复文档ID"):
                load_xfund_documents(annotation_path)

    def test_rejects_image_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            images_dir = Path(directory) / "images"
            images_dir.mkdir()
            document = _document("doc-1", "../private.png")

            with self.assertRaisesRegex(DataFormatError, "不安全路径"):
                resolve_image_path(images_dir, document)


def _document(document_id: str, image_name: str) -> dict:
    return {
        "id": document_id,
        "img": {"fname": image_name},
        "document": [
            {
                "id": 1,
                "text": "字段",
                "label": "question",
                "linking": [],
                "words": [{"text": "字段", "box": [0, 0, 10, 10]}],
            }
        ],
    }


if __name__ == "__main__":
    unittest.main()
