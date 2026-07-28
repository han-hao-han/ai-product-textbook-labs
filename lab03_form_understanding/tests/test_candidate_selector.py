from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.candidate_gallery import write_candidate_outputs
from src.candidate_selector import ROLE_LABELS, select_candidates


class CandidateSelectorTests(unittest.TestCase):
    def test_selects_five_unique_candidates_without_model_results(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            images_dir = root / "images"
            images_dir.mkdir()
            documents = []
            for index in range(6):
                image_name = f"doc-{index}.png"
                (images_dir / image_name).write_bytes(b"mock-image")
                documents.append(_document(index, image_name, pair_count=index + 2))

            candidates = select_candidates(documents, images_dir, candidate_count=5)

        self.assertEqual(len(candidates), 5)
        self.assertEqual(len({item["sample_id"] for item in candidates}), 5)
        self.assertEqual(tuple(item["candidate_role"] for item in candidates), ROLE_LABELS)
        for candidate in candidates:
            self.assertNotIn("accuracy", candidate)
            self.assertNotIn("model", candidate)

    def test_writes_local_manifest_and_human_readable_gallery(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            images_dir = root / "data" / "raw"
            images_dir.mkdir(parents=True)
            documents = []
            for index in range(6):
                image_name = f"doc-{index}.png"
                (images_dir / image_name).write_bytes(b"mock-image")
                documents.append(_document(index, image_name, pair_count=index + 2))
            candidates = select_candidates(documents, images_dir, candidate_count=5)

            manifest, gallery = write_candidate_outputs(
                candidates,
                output_dir=root / "data" / "local",
                project_root=root,
            )
            manifest_text = manifest.read_text(encoding="utf-8")
            gallery_text = gallery.read_text(encoding="utf-8")

        self.assertIn("候选，尚未由用户选择", manifest_text)
        self.assertIn("人工标注参考字段", gallery_text)
        self.assertNotIn(str(root), gallery_text)


def _document(index: int, image_name: str, pair_count: int) -> dict:
    entities = []
    for pair_index in range(pair_count):
        question_id = pair_index * 2 + 1
        answer_id = pair_index * 2 + 2
        link = [[question_id, answer_id]]
        y = 20 + pair_index * 25
        entities.extend(
            [
                {
                    "id": question_id,
                    "text": f"字段{pair_index}",
                    "label": "question",
                    "linking": link,
                    "words": [
                        {"text": f"字段{pair_index}", "box": [10, y, 90, y + 15]}
                    ],
                },
                {
                    "id": answer_id,
                    "text": "值" * (index + pair_index + 1),
                    "label": "answer",
                    "linking": link,
                    "words": [
                        {
                            "text": "值",
                            "box": [120 + index * 10, y, 180 + index * 10, y + 15],
                        }
                    ],
                },
            ]
        )
    return {
        "id": f"doc-{index}",
        "img": {"fname": image_name, "width": 300, "height": 400},
        "document": entities,
    }


if __name__ == "__main__":
    unittest.main()
