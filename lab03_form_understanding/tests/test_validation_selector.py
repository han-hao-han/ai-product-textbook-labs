from __future__ import annotations

import tempfile
import unittest
from collections import Counter
from pathlib import Path

from src.validation_gallery import write_validation_candidate_outputs
from src.validation_selector import (
    DIFFICULTY_GROUPS,
    FEATURE_WEIGHTS,
    select_validation_candidates,
)


class ValidationSelectorTests(unittest.TestCase):
    def test_generates_four_candidates_per_group_without_overlap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            images_dir = root / "images"
            images_dir.mkdir()
            documents = []
            for index in range(30):
                image_name = f"doc-{index}.png"
                (images_dir / image_name).write_bytes(b"mock-image")
                documents.append(_document(index, image_name))
            excluded = {"doc-0", "doc-1", "doc-2", "doc-3"}

            candidates = select_validation_candidates(
                documents,
                images_dir,
                excluded_ids=excluded,
            )

        counts = Counter(item["difficulty_group"] for item in candidates)
        self.assertEqual(len(candidates), 12)
        self.assertEqual(counts, Counter({group: 4 for group in DIFFICULTY_GROUPS}))
        self.assertEqual(len({item["sample_id"] for item in candidates}), 12)
        self.assertFalse({item["sample_id"] for item in candidates} & excluded)
        for candidate in candidates:
            self.assertNotIn("model", candidate)
            self.assertNotIn("accuracy", candidate)
            self.assertEqual(
                set(candidate["difficulty_details"]["feature_weights"]),
                set(FEATURE_WEIGHTS),
            )

    def test_difficulty_groups_follow_score_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            images_dir = root / "images"
            images_dir.mkdir()
            documents = []
            for index in range(30):
                image_name = f"doc-{index}.png"
                (images_dir / image_name).write_bytes(b"mock-image")
                documents.append(_document(index, image_name))
            candidates = select_validation_candidates(
                documents,
                images_dir,
                excluded_ids=set(),
            )

        scores = {
            group: [
                item["difficulty_score"]
                for item in candidates
                if item["difficulty_group"] == group
            ]
            for group in DIFFICULTY_GROUPS
        }
        self.assertLessEqual(max(scores["simple"]), min(scores["medium"]))
        self.assertLessEqual(max(scores["medium"]), min(scores["complex"]))

    def test_writes_local_validation_gallery_without_absolute_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            images_dir = root / "data" / "raw"
            images_dir.mkdir(parents=True)
            documents = []
            for index in range(30):
                image_name = f"doc-{index}.png"
                (images_dir / image_name).write_bytes(b"mock-image")
                documents.append(_document(index, image_name))
            candidates = select_validation_candidates(
                documents,
                images_dir,
                excluded_ids={"doc-0", "doc-1", "doc-2", "doc-3"},
            )

            manifest, gallery = write_validation_candidate_outputs(
                candidates,
                output_dir=root / "data" / "local",
                project_root=root,
                excluded_ids={"doc-0", "doc-1", "doc-2", "doc-3"},
            )
            manifest_text = manifest.read_text(encoding="utf-8")
            gallery_text = gallery.read_text(encoding="utf-8")

        self.assertIn("等待用户每类选择2张", manifest_text)
        self.assertIn("难度贡献明细", gallery_text)
        self.assertNotIn(str(root), gallery_text)


def _document(index: int, image_name: str) -> dict:
    pair_count = index % 10 + 2
    entities = []
    for pair_index in range(pair_count):
        question_id = pair_index * 2 + 1
        answer_id = pair_index * 2 + 2
        link = [[question_id, answer_id]]
        y = 15 + pair_index * 25
        question_text = "重复字段" if index % 5 == 0 else f"字段{pair_index}"
        answer_text = "值" * (1 + index + pair_index)
        answer_words = [
            {"text": answer_text, "box": [120 + index, y, 220 + index, y + 12]}
        ]
        if index % 4 == 0:
            answer_words.append(
                {"text": "第二行", "box": [120 + index, y + 20, 190 + index, y + 32]}
            )
        entities.extend(
            [
                {
                    "id": question_id,
                    "text": question_text,
                    "label": "question",
                    "linking": link,
                    "words": [
                        {"text": question_text, "box": [10, y, 90, y + 12]}
                    ],
                },
                {
                    "id": answer_id,
                    "text": answer_text,
                    "label": "answer",
                    "linking": link,
                    "words": answer_words,
                },
            ]
        )
    return {
        "id": f"doc-{index}",
        "img": {"fname": image_name, "width": 400, "height": 500},
        "document": entities,
    }


if __name__ == "__main__":
    unittest.main()
