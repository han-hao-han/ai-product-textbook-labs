from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from openai import OpenAI, OpenAIError
from pydantic import ValidationError

from common.config import (
    LLMSettings,
    load_llm_settings,
)
from common.llm_client import create_openai_client
from src.json_parser import (
    JSONOutputError,
    format_validation_error,
    parse_feedback_analysis,
)
from src.prompts import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    build_user_prompt,
)
from src.schemas import FeedbackAnalysis
from src.validators import (
    ValidationIssue,
    validate_analysis_output,
)


@dataclass(frozen=True)
class AnalysisRun:
    """一次经过完整校验的模型分析结果。"""

    result: FeedbackAnalysis
    raw_content: str
    model_requested: str
    model_returned: str
    prompt_version: str
    elapsed_seconds: float
    usage: dict[str, int | None]


class FeedbackAnalyzerError(RuntimeError):
    """用户反馈分析过程中的统一异常。"""

    def __init__(
        self,
        message: str,
        *,
        code: str,
        issues: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)

        self.code = code
        self.issues = issues or []


def usage_to_dict(
    usage: Any,
) -> dict[str, int | None]:
    """将 OpenAI-compatible Token 统计转换为字典。"""
    if usage is None:
        return {
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
        }

    return {
        "prompt_tokens": getattr(
            usage,
            "prompt_tokens",
            None,
        ),
        "completion_tokens": getattr(
            usage,
            "completion_tokens",
            None,
        ),
        "total_tokens": getattr(
            usage,
            "total_tokens",
            None,
        ),
    }


def issues_to_dicts(
    issues: list[ValidationIssue],
) -> list[dict[str, str]]:
    """将业务校验问题转换为可序列化结构。"""
    return [
        {
            "code": issue.code,
            "field_path": issue.field_path,
            "message": issue.message,
        }
        for issue in issues
    ]


class FeedbackAnalyzer:
    """
    用户反馈分析器。

    负责完成：

    1. Prompt 构造；
    2. 大模型 API 请求；
    3. JSON 解析；
    4. Pydantic Schema 校验；
    5. review_id、连续原文证据和业务规则校验。
    """

    def __init__(
        self,
        settings: LLMSettings | None = None,
        client: OpenAI | None = None,
    ) -> None:
        self.settings = (
            settings
            if settings is not None
            else load_llm_settings()
        )

        self.client = (
            client
            if client is not None
            else create_openai_client(
                self.settings
            )
        )

    def _provider_extra_body(
        self,
    ) -> dict[str, Any]:
        """
        返回不同 OpenAI-compatible 服务的附加参数。

        正式实验默认使用 DeepSeek。其他分支用于保留接口
        可替换性，但不改变本实验的默认模型选型。
        """
        base_url = self.settings.base_url.lower()

        if "api.deepseek.com" in base_url:
            return {
                "thinking": {
                    "type": "disabled",
                }
            }

        if (
            "dashscope.aliyuncs.com" in base_url
            or "maas.aliyuncs.com" in base_url
        ):
            return {
                "enable_thinking": False,
            }

        if "bigmodel.cn" in base_url:
            return {
                "thinking": {
                    "type": "disabled",
                }
            }

        return {}

    def analyze(
        self,
        review_id: str,
        review_text: str,
    ) -> AnalysisRun:
        """
        分析一条评论并返回经过完整校验的结果。

        如果 API、JSON、Schema 或证据校验失败，会抛出
        FeedbackAnalyzerError，而不是返回未经验证的数据。
        """
        normalized_review_id = str(
            review_id
        ).strip()

        normalized_review_text = str(
            review_text
        ).strip()

        if not normalized_review_id:
            raise FeedbackAnalyzerError(
                "review_id 不能为空",
                code="empty_review_id",
            )

        if not normalized_review_text:
            raise FeedbackAnalyzerError(
                "review_text 不能为空",
                code="empty_review_text",
            )

        user_prompt = build_user_prompt(
            review_id=normalized_review_id,
            review_text=normalized_review_text,
        )

        request_arguments: dict[str, Any] = {
            "model": self.settings.model,
            "messages": [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
            "temperature": (
                self.settings.temperature
            ),
            "response_format": {
                "type": "json_object",
            },
            "max_completion_tokens": 1500,
            "stream": False,
        }

        extra_body = self._provider_extra_body()

        if extra_body:
            request_arguments[
                "extra_body"
            ] = extra_body

        started_at = time.perf_counter()

        try:
            response = (
                self.client
                .chat
                .completions
                .create(
                    **request_arguments
                )
            )
        except OpenAIError as error:
            elapsed_seconds = round(
                time.perf_counter()
                - started_at,
                3,
            )

            raise FeedbackAnalyzerError(
                (
                    "大模型 API 调用失败："
                    f"{type(error).__name__}: "
                    f"{error}"
                ),
                code="api_error",
                issues=[
                    {
                        "code": "api_error",
                        "field_path": "api",
                        "message": str(error),
                        "elapsed_seconds": (
                            elapsed_seconds
                        ),
                    }
                ],
            ) from error

        elapsed_seconds = round(
            time.perf_counter() - started_at,
            3,
        )

        if not response.choices:
            raise FeedbackAnalyzerError(
                "模型响应中没有 choices",
                code="empty_choices",
            )

        choice = response.choices[0]

        raw_content = (
            choice.message.content or ""
        ).strip()

        if not raw_content:
            raise FeedbackAnalyzerError(
                "模型返回内容为空",
                code="empty_content",
            )

        try:
            result = parse_feedback_analysis(
                raw_content
            )
        except JSONOutputError as error:
            raise FeedbackAnalyzerError(
                f"模型 JSON 输出无效：{error}",
                code="invalid_json",
                issues=[
                    {
                        "code": "invalid_json",
                        "field_path": (
                            "raw_content"
                        ),
                        "message": str(error),
                    }
                ],
            ) from error
        except ValidationError as error:
            schema_issues = (
                format_validation_error(error)
            )

            raise FeedbackAnalyzerError(
                "模型输出不符合数据结构要求",
                code="schema_validation_failed",
                issues=schema_issues,
            ) from error

        validation_issues = (
            validate_analysis_output(
                result=result,
                expected_review_id=(
                    normalized_review_id
                ),
                review_text=(
                    normalized_review_text
                ),
            )
        )

        if validation_issues:
            serialized_issues = (
                issues_to_dicts(
                    validation_issues
                )
            )

            raise FeedbackAnalyzerError(
                "模型输出未通过证据或业务校验",
                code="business_validation_failed",
                issues=serialized_issues,
            )

        returned_model = str(
            getattr(
                response,
                "model",
                self.settings.model,
            )
        )

        return AnalysisRun(
            result=result,
            raw_content=raw_content,
            model_requested=(
                self.settings.model
            ),
            model_returned=returned_model,
            prompt_version=PROMPT_VERSION,
            elapsed_seconds=elapsed_seconds,
            usage=usage_to_dict(
                response.usage
            ),
        )