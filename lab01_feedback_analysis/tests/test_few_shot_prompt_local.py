from __future__ import annotations

import sys
from pathlib import Path


LAB_DIR = Path(__file__).resolve().parents[1]

if str(LAB_DIR) not in sys.path:
    sys.path.insert(0, str(LAB_DIR))


from src.prompts import (
    FEW_SHOT_INPUT,
    FEW_SHOT_OUTPUT,
    PROMPT_VERSION,
    build_user_prompt,
)
from src.schemas import FeedbackAnalysis
from src.validators import validate_analysis_output


def test_few_shot_schema() -> None:
    result = FeedbackAnalysis.model_validate(
        FEW_SHOT_OUTPUT
    )

    issues = validate_analysis_output(
        result=result,
        expected_review_id=(
            FEW_SHOT_INPUT["review_id"]
        ),
        review_text=(
            FEW_SHOT_INPUT["review_text"]
        ),
    )

    assert issues == [], issues

    predicted_aspects = {
        aspect.aspect.value: (
            aspect.sentiment.value
        )
        for aspect in result.aspects
    }

    assert predicted_aspects["price"] == "mixed"
    assert result.issue_summary
    assert result.suggested_action

    print("FEW_SHOT_SCHEMA_OK")
    print("FEW_SHOT_SEMANTIC_RULE_OK")


def test_prompt_build() -> None:
    actual_review_id = "actual-review-001"

    actual_review_text = (
        "味道不错，但优惠券使用不方便。"
    )

    prompt = build_user_prompt(
        review_id=actual_review_id,
        review_text=actual_review_text,
    )

    assert PROMPT_VERSION in (
        "v2_positive_constraint_few_shot",
    )

    assert FEW_SHOT_INPUT[
        "review_text"
    ] in prompt

    assert actual_review_text in prompt
    assert actual_review_id in prompt
    assert '"sentiment": "mixed"' in prompt
    assert "老年卡" in prompt
    assert "规则示例" in prompt

    print("PROMPT_V2_BUILD_OK")


def main() -> None:
    test_few_shot_schema()
    test_prompt_build()

    print("FEW_SHOT_PROMPT_LOCAL_TESTS_OK")


if __name__ == "__main__":
    main()