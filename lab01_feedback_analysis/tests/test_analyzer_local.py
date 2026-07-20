from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock



LAB_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = LAB_DIR.parent

for path in (REPOSITORY_ROOT, LAB_DIR):
    path_text = str(path)

    if path_text not in sys.path:
        sys.path.insert(0, path_text)


from common.config import LLMSettings
from src.analyzer import (
    FeedbackAnalyzer,
    FeedbackAnalyzerError,
)


def make_settings(
    base_url: str = "https://api.deepseek.com",
) -> LLMSettings:
    return LLMSettings(
        api_key="test-key",
        base_url=base_url,
        model="test-model",
        temperature=0.0,
    )


def test_empty_review_id() -> None:
    analyzer = FeedbackAnalyzer(
        settings=make_settings(),
        client=Mock(),
    )

    try:
        analyzer.analyze(
            review_id="",
            review_text="评论内容",
        )
    except FeedbackAnalyzerError as error:
        assert error.code == "empty_review_id"
    else:
        raise AssertionError(
            "空 review_id 应触发异常"
        )

    print("EMPTY_REVIEW_ID_REJECTED")


def test_empty_review_text() -> None:
    analyzer = FeedbackAnalyzer(
        settings=make_settings(),
        client=Mock(),
    )

    try:
        analyzer.analyze(
            review_id="1",
            review_text="",
        )
    except FeedbackAnalyzerError as error:
        assert error.code == "empty_review_text"
    else:
        raise AssertionError(
            "空 review_text 应触发异常"
        )

    print("EMPTY_REVIEW_TEXT_REJECTED")


def test_provider_extra_body() -> None:
    deepseek = FeedbackAnalyzer(
        settings=make_settings(
            "https://api.deepseek.com"
        ),
        client=Mock(),
    )

    assert deepseek._provider_extra_body() == {
        "thinking": {
            "type": "disabled",
        }
    }

    qwen = FeedbackAnalyzer(
        settings=make_settings(
            (
                "https://dashscope.aliyuncs.com/"
                "compatible-mode/v1"
            )
        ),
        client=Mock(),
    )

    assert qwen._provider_extra_body() == {
        "enable_thinking": False,
    }

    glm = FeedbackAnalyzer(
        settings=make_settings(
            (
                "https://open.bigmodel.cn/"
                "api/paas/v4/"
            )
        ),
        client=Mock(),
    )

    assert glm._provider_extra_body() == {
        "thinking": {
            "type": "disabled",
        }
    }

    print("PROVIDER_EXTRA_BODY_OK")


def test_valid_model_response() -> None:
    raw_content = """
    {
      "review_id": "test-001",
      "overall_sentiment": "mixed",
      "aspects": [
        {
          "aspect": "service",
          "sentiment": "negative",
          "evidence": "服务态度很差"
        },
        {
          "aspect": "food",
          "sentiment": "positive",
          "evidence": "菜品味道不错"
        }
      ],
      "issue_summary": "服务态度较差。",
      "suggested_action": "加强服务培训。"
    }
    """.strip()

    response = SimpleNamespace(
        model="test-model",
        usage=SimpleNamespace(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        ),
        choices=[
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(
                    content=raw_content
                ),
            )
        ],
    )

    create_method = Mock(
        return_value=response
    )

    mock_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=create_method
            )
        )
    )

    analyzer = FeedbackAnalyzer(
        settings=make_settings(),
        client=mock_client,
    )

    review_text = (
        "服务态度很差，但是菜品味道不错"
    )

    run = analyzer.analyze(
        review_id="test-001",
        review_text=review_text,
    )

    assert (
        run.result.review_id
        == "test-001"
    )

    assert (
        run.result.overall_sentiment.value
        == "mixed"
    )

    assert run.usage["total_tokens"] == 150

    request_arguments = (
        create_method.call_args.kwargs
    )

    assert request_arguments[
        "response_format"
    ] == {
        "type": "json_object",
    }

    assert request_arguments[
        "extra_body"
    ] == {
        "thinking": {
            "type": "disabled",
        }
    }

    print("VALID_MODEL_RESPONSE_OK")


def test_invalid_evidence_rejected() -> None:
    raw_content = """
    {
      "review_id": "test-002",
      "overall_sentiment": "negative",
      "aspects": [
        {
          "aspect": "service",
          "sentiment": "negative",
          "evidence": "服务很差..."
        }
      ],
      "issue_summary": "服务较差。",
      "suggested_action": "改善服务。"
    }
    """.strip()

    response = SimpleNamespace(
        model="test-model",
        usage=None,
        choices=[
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(
                    content=raw_content
                ),
            )
        ],
    )

    mock_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=Mock(
                    return_value=response
                )
            )
        )
    )

    analyzer = FeedbackAnalyzer(
        settings=make_settings(),
        client=mock_client,
    )

    try:
        analyzer.analyze(
            review_id="test-002",
            review_text="服务很差",
        )
    except FeedbackAnalyzerError as error:
        assert (
            error.code
            == "business_validation_failed"
        )

        assert any(
            issue["code"]
            == "evidence_not_found"
            for issue in error.issues
        )
    else:
        raise AssertionError(
            "非连续原文证据应被拒绝"
        )

    print("INVALID_EVIDENCE_REJECTED")


def main() -> None:
    test_empty_review_id()
    test_empty_review_text()
    test_provider_extra_body()
    test_valid_model_response()
    test_invalid_evidence_rejected()

    print("ANALYZER_LOCAL_TESTS_OK")


if __name__ == "__main__":
    main()