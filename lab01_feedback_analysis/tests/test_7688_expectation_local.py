from __future__ import annotations

import json
import sys
from pathlib import Path


LAB_DIR = Path(__file__).resolve().parents[1]

if str(LAB_DIR) not in sys.path:
    sys.path.insert(0, str(LAB_DIR))


from src.prompts import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
)
from src.schemas import FeedbackAnalysis
from src.semantic_checks import (
    validate_semantic_expectation,
)


MODEL_TEST_DIR = (
    LAB_DIR
    / "expected_outputs"
    / "model_tests"
)

EXPECTATION_PATH = (
    LAB_DIR
    / "expected_outputs"
    / "semantic_expectations.json"
)


def find_latest_v2_result() -> Path:
    files = sorted(
        MODEL_TEST_DIR.glob(
            "deepseek_demo_v2_regression_*.json"
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    if not files:
        raise FileNotFoundError(
            "没有找到 V2 回归测试 JSON"
        )

    return files[0]


def main() -> None:
    assert PROMPT_VERSION == "v3_billing_consistency"
    assert "收费金额与点单价格不一致" in SYSTEM_PROMPT
    assert "price 必须标记为 mixed" in SYSTEM_PROMPT

    result_path = find_latest_v2_result()

    test_data = json.loads(
        result_path.read_text(
            encoding="utf-8"
        )
    )

    expectation_data = json.loads(
        EXPECTATION_PATH.read_text(
            encoding="utf-8"
        )
    )

    record = next(
        item
        for item in test_data["records"]
        if item["review_id"] == "7688"
    )

    result = FeedbackAnalysis.model_validate(
        record["parsed_result"]
    )

    expectation = (
        expectation_data["reviews"]["7688"]
    )

    issues = validate_semantic_expectation(
        result=result,
        expectation=expectation,
    )

    assert issues, (
        "旧版 7688 结果应被新的语义标准拒绝"
    )

    assert any(
        issue.code
        in {
            "required_aspect_missing",
            "unexpected_aspect_sentiment",
        }
        for issue in issues
    ), issues

    print("=== 7688 旧结果重新评估 ===")

    for issue in issues:
        print(
            f"- [{issue.code}] "
            f"{issue.field_path}: "
            f"{issue.message}"
        )

    print("PROMPT_V3_RULES_OK")
    print("OLD_7688_RESULT_REJECTED")
    print("SEMANTIC_EXPECTATION_GAP_FIXED")


if __name__ == "__main__":
    main()