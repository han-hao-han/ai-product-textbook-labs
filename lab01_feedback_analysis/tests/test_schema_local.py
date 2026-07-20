from __future__ import annotations

import sys
from pathlib import Path

from pydantic import ValidationError


LAB_DIR = Path(__file__).resolve().parents[1]

if str(LAB_DIR) not in sys.path:
    sys.path.insert(0, str(LAB_DIR))


from src.schemas import FeedbackAnalysis
from src.validators import validate_analysis_output


REVIEW_ID = "7688"

REVIEW_TEXT = (
    "位置：这里的位置非常好找，就在铁三附近，就可以看到诚胜和的"
    "红色巨大招牌。服务：这里的服务我不得不说真的是很不好，也许"
    "是因为这里在学校旁边，服务起来有一种暴力模式，因为今天是"
    "第一次去不太清楚点饭模式，但是服务人员就很凶，本来点的是"
    "8块钱的三鲜馄饨，付钱的时候要了12，我说我要的是三鲜馄饨，"
    "她说汤是三鲜的，馄饨是大肉的，这种狡辩让我很不开心。"
    "环境：这里的环境还算干净整洁，店面相对也比较大，整体比较"
    "规规矩矩和大多数店差不多的。口味：这家上饭速度很不错，"
    "挺快的，饺子里的馅也挺多的挺实在的，中午学生在这里挺实惠"
    "的。总之这家是一家不错的店，就是服务态度需要改善。"
)


VALID_PAYLOAD = {
    "review_id": REVIEW_ID,
    "overall_sentiment": "mixed",
    "aspects": [
        {
            "aspect": "location",
            "sentiment": "positive",
            # 测试 Schema 是否能清理模型额外添加的引号。
            "evidence": "“这里的位置非常好找”",
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
        "加强服务沟通培训，并在顾客付款前明确订单和价格。"
    ),
}


def test_valid_payload() -> FeedbackAnalysis:
    result = FeedbackAnalysis.model_validate(
        VALID_PAYLOAD
    )

    issues = validate_analysis_output(
        result=result,
        expected_review_id=REVIEW_ID,
        review_text=REVIEW_TEXT,
    )

    assert issues == [], issues

    assert (
        result.aspects[0].evidence
        == "这里的位置非常好找"
    )

    print("VALID_SCHEMA_OK")
    print("EVIDENCE_VALIDATION_OK")

    return result


def test_invalid_enum() -> None:
    invalid_payload = {
        **VALID_PAYLOAD,
        "overall_sentiment": "very_good",
    }

    try:
        FeedbackAnalysis.model_validate(
            invalid_payload
        )
    except ValidationError:
        print("INVALID_ENUM_REJECTED")
        return

    raise AssertionError(
        "非法情感枚举未被 Pydantic 拒绝"
    )


def test_invalid_evidence(
    valid_result: FeedbackAnalysis,
) -> None:
    invalid_result = valid_result.model_copy(
        deep=True
    )

    invalid_result.aspects[0].evidence = (
        "餐厅紧邻地铁站"
    )

    issues = validate_analysis_output(
        result=invalid_result,
        expected_review_id=REVIEW_ID,
        review_text=REVIEW_TEXT,
    )

    assert any(
        issue.code == "evidence_not_found"
        for issue in issues
    ), issues

    print("INVALID_EVIDENCE_REJECTED")


def test_review_id_mismatch(
    valid_result: FeedbackAnalysis,
) -> None:
    issues = validate_analysis_output(
        result=valid_result,
        expected_review_id="OTHER_ID",
        review_text=REVIEW_TEXT,
    )

    assert any(
        issue.code == "review_id_mismatch"
        for issue in issues
    ), issues

    print("REVIEW_ID_MISMATCH_REJECTED")


def main() -> None:
    valid_result = test_valid_payload()

    test_invalid_enum()
    test_invalid_evidence(valid_result)
    test_review_id_mismatch(valid_result)

    print("LOCAL_VALIDATION_TESTS_OK")


if __name__ == "__main__":
    main()