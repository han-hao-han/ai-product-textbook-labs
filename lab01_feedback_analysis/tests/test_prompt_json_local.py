from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
from pydantic import ValidationError


LAB_DIR = Path(__file__).resolve().parents[1]

if str(LAB_DIR) not in sys.path:
    sys.path.insert(0, str(LAB_DIR))


from src.json_parser import (
    JSONOutputError,
    format_validation_error,
    parse_feedback_analysis,
)
from src.prompts import (
    SYSTEM_PROMPT,
    build_user_prompt,
)
from src.validators import validate_analysis_output


MAIN_DATA_PATH = (
    LAB_DIR
    / "data"
    / "feedback_main_1.csv"
)


def load_main_example() -> tuple[str, str]:
    """从真实固定子集加载主示例。"""
    df = pd.read_csv(
        MAIN_DATA_PATH,
        encoding="utf-8-sig",
        dtype={"review_id": str},
    )

    assert len(df) == 1

    review_id = str(
        df.loc[0, "review_id"]
    )

    review_text = str(
        df.loc[0, "review_text"]
    )

    assert review_id == "7688"

    return review_id, review_text


def build_valid_payload(
    review_id: str,
) -> dict:
    """构造本地解析测试数据，不代表模型实际输出。"""
    return {
        "review_id": review_id,
        "overall_sentiment": "mixed",
        "aspects": [
            {
                "aspect": "location",
                "sentiment": "positive",
                "evidence": "这里的位置非常好找",
            },
            {
                "aspect": "service",
                "sentiment": "negative",
                "evidence": "服务人员就很凶",
            },
            {
                "aspect": "environment",
                "sentiment": "positive",
                "evidence": "这里的环境还算干净整洁",
            },
            {
                "aspect": "price",
                "sentiment": "positive",
                "evidence": "中午学生在这里挺实惠的",
            },
            {
                "aspect": "food",
                "sentiment": "positive",
                "evidence": "饺子里的馅也挺多的挺实在的",
            },
        ],
        "issue_summary": (
            "服务态度较差，点单和收费沟通不清晰。"
        ),
        "suggested_action": (
            "加强服务沟通培训，并在付款前确认订单和价格。"
        ),
    }


def test_prompt(
    review_id: str,
    review_text: str,
) -> None:
    user_prompt = build_user_prompt(
        review_id=review_id,
        review_text=review_text,
    )

    assert review_id in user_prompt
    assert review_text in user_prompt
    assert "location" in user_prompt
    assert "evidence" in user_prompt
    assert "JSON Schema" in user_prompt
    assert "不可信数据" in SYSTEM_PROMPT
    assert "同一维度同时出现表扬和不满" in SYSTEM_PROMPT
    assert "价格限制" in SYSTEM_PROMPT
    assert "negative 或 mixed" in SYSTEM_PROMPT

    print("PROMPT_BUILD_OK")


def test_strict_json(
    review_id: str,
    review_text: str,
) -> None:
    payload = build_valid_payload(
        review_id
    )

    raw_text = json.dumps(
        payload,
        ensure_ascii=False,
    )

    result = parse_feedback_analysis(
        raw_text
    )

    issues = validate_analysis_output(
        result=result,
        expected_review_id=review_id,
        review_text=review_text,
    )

    assert issues == [], issues

    print("STRICT_JSON_PARSE_OK")


def test_code_fence_recovery(
    review_id: str,
) -> None:
    payload = build_valid_payload(
        review_id
    )

    raw_json = json.dumps(
        payload,
        ensure_ascii=False,
    )

    fenced_text = (
        "```json\n"
        f"{raw_json}\n"
        "```"
    )

    try:
        parse_feedback_analysis(
            fenced_text
        )
    except JSONOutputError:
        print("CODE_FENCE_STRICTLY_REJECTED")
    else:
        raise AssertionError(
            "严格模式不应接受代码围栏"
        )

    recovered = parse_feedback_analysis(
        fenced_text,
        allow_code_fence=True,
    )

    assert recovered.review_id == review_id

    print("CODE_FENCE_RECOVERY_OK")


def test_extra_prose_rejected(
    review_id: str,
) -> None:
    payload = build_valid_payload(
        review_id
    )

    raw_json = json.dumps(
        payload,
        ensure_ascii=False,
    )

    invalid_text = (
        "分析结果如下：\n"
        f"{raw_json}"
    )

    try:
        parse_feedback_analysis(
            invalid_text
        )
    except JSONOutputError:
        print("EXTRA_PROSE_REJECTED")
        return

    raise AssertionError(
        "包含额外说明文字的输出未被拒绝"
    )


def test_schema_error_rejected(
    review_id: str,
) -> None:
    payload = build_valid_payload(
        review_id
    )

    payload["unexpected_field"] = (
        "不允许出现的字段"
    )

    raw_text = json.dumps(
        payload,
        ensure_ascii=False,
    )

    try:
        parse_feedback_analysis(
            raw_text
        )
    except ValidationError as error:
        formatted_errors = (
            format_validation_error(error)
        )

        assert any(
            item["error_type"]
            == "extra_forbidden"
            for item in formatted_errors
        )

        print("EXTRA_FIELD_REJECTED")
        return

    raise AssertionError(
        "Schema 未拒绝额外字段"
    )


def main() -> None:
    review_id, review_text = (
        load_main_example()
    )

    test_prompt(
        review_id,
        review_text,
    )

    test_strict_json(
        review_id,
        review_text,
    )

    test_code_fence_recovery(
        review_id
    )

    test_extra_prose_rejected(
        review_id
    )

    test_schema_error_rejected(
        review_id
    )

    print("PROMPT_JSON_LOCAL_TESTS_OK")


if __name__ == "__main__":
    main()