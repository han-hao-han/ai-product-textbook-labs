from __future__ import annotations

import unittest

from src.prompt_loader import load_extraction_prompt


class PromptContractTests(unittest.TestCase):
    def test_prompt_contains_required_boundaries(self) -> None:
        prompt = load_extraction_prompt()
        for required_text in (
            "fields",
            "warnings",
            "JSON",
            "不根据常识补全",
            "不输出分析过程",
            "不使用 Markdown 代码围栏",
            "不得输出样本ID、置信度、评分、比较状态或人工标注参考结果",
        ):
            self.assertIn(required_text, prompt)


if __name__ == "__main__":
    unittest.main()
