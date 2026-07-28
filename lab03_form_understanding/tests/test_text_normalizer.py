from __future__ import annotations

import unittest

from src.text_normalizer import normalize_text


class TextNormalizerTests(unittest.TestCase):
    def test_normalizes_fullwidth_characters(self) -> None:
        self.assertEqual(normalize_text("ＡＢＣ１２３：中国"), "ABC123:中国")

    def test_collapses_whitespace_and_unifies_newlines(self) -> None:
        self.assertEqual(normalize_text("  第一行\r\n  第二行  "), "第一行 第二行")

    def test_removes_only_trailing_key_colons(self) -> None:
        self.assertEqual(normalize_text("联系电话：  ", is_key=True), "联系电话")
        self.assertEqual(normalize_text("比例：1", is_key=True), "比例:1")


if __name__ == "__main__":
    unittest.main()
