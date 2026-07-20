from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence


LAB_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = LAB_DIR.parent

for path in (REPOSITORY_ROOT, LAB_DIR):
    path_text = str(path)

    if path_text not in sys.path:
        sys.path.insert(0, path_text)


from src.analyzer import (
    AnalysisRun,
    FeedbackAnalyzer,
    FeedbackAnalyzerError,
)


def build_parser() -> argparse.ArgumentParser:
    """构造命令行参数解析器。"""
    parser = argparse.ArgumentParser(
        description=(
            "调用大模型分析一条餐饮用户评论，"
            "输出情感、评价维度、原文证据和改进建议。"
        )
    )

    parser.add_argument(
        "--review-id",
        required=True,
        help="评论唯一 ID，例如 7688",
    )

    parser.add_argument(
        "--text",
        required=True,
        help="待分析的完整评论文本",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="以 JSON 格式输出完整结果",
    )

    parser.add_argument(
        "--show-metadata",
        action="store_true",
        help="在人类可读模式下显示模型、耗时和 Token 信息",
    )

    return parser


def build_output_data(
    run: AnalysisRun,
) -> dict:
    """将分析结果转换为可序列化字典。"""
    return {
        "analysis": run.result.model_dump(
            mode="json"
        ),
        "metadata": {
            "model_requested": (
                run.model_requested
            ),
            "model_returned": (
                run.model_returned
            ),
            "prompt_version": (
                run.prompt_version
            ),
            "elapsed_seconds": (
                run.elapsed_seconds
            ),
            "usage": run.usage,
        },
    }


def print_human_readable(
    run: AnalysisRun,
    *,
    show_metadata: bool,
) -> None:
    """输出便于终端阅读的分析结果。"""
    result = run.result

    print("=== 用户反馈分析结果 ===")
    print(f"评论 ID：{result.review_id}")
    print(
        "总体情感："
        f"{result.overall_sentiment.value}"
    )

    print()
    print("评价维度：")

    if not result.aspects:
        print("- 未识别到明确评价维度")
    else:
        for aspect in result.aspects:
            print(
                f"- {aspect.aspect.value}: "
                f"{aspect.sentiment.value}"
            )
            print(
                f"  证据：{aspect.evidence}"
            )

    print()
    print(
        "问题概括："
        + (
            result.issue_summary
            if result.issue_summary
            else "无明确问题"
        )
    )

    print(
        "改进建议："
        + (
            result.suggested_action
            if result.suggested_action
            else "无"
        )
    )

    if show_metadata:
        print()
        print("=== 运行信息 ===")
        print(
            f"请求模型："
            f"{run.model_requested}"
        )
        print(
            f"返回模型："
            f"{run.model_returned}"
        )
        print(
            f"Prompt 版本："
            f"{run.prompt_version}"
        )
        print(
            f"耗时："
            f"{run.elapsed_seconds} 秒"
        )
        print(
            "Token："
            f"{run.usage}"
        )


def print_error(
    error: FeedbackAnalyzerError,
    *,
    json_output: bool,
) -> None:
    """输出统一错误信息。"""
    error_data = {
        "error": {
            "code": error.code,
            "message": str(error),
            "issues": error.issues,
        }
    }

    if json_output:
        print(
            json.dumps(
                error_data,
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return

    print(
        f"分析失败 [{error.code}]："
        f"{error}",
        file=sys.stderr,
    )

    for issue in error.issues:
        issue_code = (
            issue.get("code")
            or issue.get("error_type")
            or "unknown_error"
        )

        print(
            f"- [{issue_code}] "
            f"{issue.get('field_path', '')}: "
            f"{issue.get('message', '')}",
            file=sys.stderr,
        )


def main(
    argv: Sequence[str] | None = None,
) -> int:
    """命令行入口，成功返回 0，失败返回非零状态码。"""
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        analyzer = FeedbackAnalyzer()

        run = analyzer.analyze(
            review_id=args.review_id,
            review_text=args.text,
        )
    except FeedbackAnalyzerError as error:
        print_error(
            error,
            json_output=args.json_output,
        )
        return 1
    except Exception as error:
        unexpected_error = (
            FeedbackAnalyzerError(
                (
                    "发生未预期错误："
                    f"{type(error).__name__}: "
                    f"{error}"
                ),
                code="unexpected_error",
            )
        )

        print_error(
            unexpected_error,
            json_output=args.json_output,
        )
        return 2

    if args.json_output:
        print(
            json.dumps(
                build_output_data(run),
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print_human_readable(
            run,
            show_metadata=(
                args.show_metadata
            ),
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())