from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

import pandas as pd


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


DEFAULT_INPUT_PATH = (
    LAB_DIR
    / "data"
    / "feedback_demo_5.csv"
)

DEFAULT_OUTPUT_DIR = (
    LAB_DIR
    / "results"
    / "batch"
)


def build_parser() -> argparse.ArgumentParser:
    """创建批量分析命令行参数。"""
    parser = argparse.ArgumentParser(
        description=(
            "读取 CSV 文件，逐条调用大模型分析用户反馈，"
            "并将结果保存为新的 CSV 文件。"
        )
    )

    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT_PATH,
        help=(
            "输入 CSV 路径，默认使用 "
            "feedback_demo_5.csv"
        ),
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "输出 CSV 路径。未指定时自动生成"
            "带时间戳的文件名。"
        ),
    )

    parser.add_argument(
        "--id-column",
        default="review_id",
        help="评论 ID 列名，默认 review_id",
    )

    parser.add_argument(
        "--text-column",
        default="review_text",
        help="评论文本列名，默认 review_text",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="只处理前 N 条，用于小规模测试",
    )

    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="任意一条失败时立即停止",
    )

    return parser


def make_default_output_path() -> Path:
    """生成带时间戳的默认输出路径。"""
    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    return (
        DEFAULT_OUTPUT_DIR
        / f"feedback_batch_{timestamp}.csv"
    )


def validate_input_dataframe(
    dataframe: pd.DataFrame,
    *,
    id_column: str,
    text_column: str,
) -> None:
    """检查输入 CSV 是否包含必要字段。"""
    missing_columns = [
        column
        for column in (
            id_column,
            text_column,
        )
        if column not in dataframe.columns
    ]

    if missing_columns:
        raise ValueError(
            "输入 CSV 缺少必要字段："
            + ", ".join(missing_columns)
        )


def build_success_fields(
    run: AnalysisRun,
) -> dict[str, Any]:
    """将成功结果展开为适合 CSV 的字段。"""
    result = run.result

    aspects_data = [
        aspect.model_dump(mode="json")
        for aspect in result.aspects
    ]

    aspect_signature = "|".join(
        (
            f"{aspect.aspect.value}:"
            f"{aspect.sentiment.value}"
        )
        for aspect in result.aspects
    )

    return {
        "analysis_status": "success",
        "analysis_error_code": "",
        "analysis_error_message": "",
        "analysis_error_issues": "",
        "overall_sentiment": (
            result.overall_sentiment.value
        ),
        "aspect_signature": aspect_signature,
        "aspects_json": json.dumps(
            aspects_data,
            ensure_ascii=False,
        ),
        "issue_summary": result.issue_summary,
        "suggested_action": (
            result.suggested_action
        ),
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
        "prompt_tokens": run.usage.get(
            "prompt_tokens"
        ),
        "completion_tokens": run.usage.get(
            "completion_tokens"
        ),
        "total_tokens": run.usage.get(
            "total_tokens"
        ),
    }


def build_error_fields(
    error: FeedbackAnalyzerError,
) -> dict[str, Any]:
    """将失败信息转换为 CSV 字段。"""
    return {
        "analysis_status": "failed",
        "analysis_error_code": error.code,
        "analysis_error_message": str(error),
        "analysis_error_issues": json.dumps(
            error.issues,
            ensure_ascii=False,
        ),
        "overall_sentiment": "",
        "aspect_signature": "",
        "aspects_json": "",
        "issue_summary": "",
        "suggested_action": "",
        "model_requested": "",
        "model_returned": "",
        "prompt_version": "",
        "elapsed_seconds": "",
        "prompt_tokens": "",
        "completion_tokens": "",
        "total_tokens": "",
    }


def save_records(
    records: list[dict[str, Any]],
    output_path: Path,
) -> None:
    """
    保存当前结果。

    每处理一条就保存一次，避免批量任务中断后
    丢失已经完成的结果。
    """
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_dataframe = pd.DataFrame(
        records
    )

    output_dataframe.to_csv(
        output_path,
        index=False,
        encoding="utf-8-sig",
    )


def process_dataframe(
    dataframe: pd.DataFrame,
    *,
    analyzer: FeedbackAnalyzer,
    output_path: Path,
    id_column: str = "review_id",
    text_column: str = "review_text",
    limit: int | None = None,
    stop_on_error: bool = False,
) -> dict[str, Any]:
    """逐行分析 DataFrame 并保存结果。"""
    validate_input_dataframe(
        dataframe,
        id_column=id_column,
        text_column=text_column,
    )

    if limit is not None:
        if limit <= 0:
            raise ValueError(
                "limit 必须是正整数"
            )

        dataframe = dataframe.head(limit)

    total_count = len(dataframe)

    if total_count == 0:
        raise ValueError(
            "输入 CSV 没有可处理的数据"
        )

    records: list[dict[str, Any]] = []

    success_count = 0
    failed_count = 0
    total_tokens = 0
    total_elapsed_seconds = 0.0

    print("=== 批量用户反馈分析 ===")
    print(f"待处理数量：{total_count}")
    print(f"输出路径：{output_path}")
    print()

    for position, (_, row) in enumerate(
        dataframe.iterrows(),
        start=1,
    ):
        review_id = str(
            row[id_column]
        ).strip()

        review_text = str(
            row[text_column]
        ).strip()

        original_fields = {
            str(column): value
            for column, value in row.items()
        }

        print(
            f"[{position}/{total_count}] "
            f"review_id={review_id}"
        )

        try:
            run = analyzer.analyze(
                review_id=review_id,
                review_text=review_text,
            )
        except FeedbackAnalyzerError as error:
            failed_count += 1

            output_record = {
                **original_fields,
                **build_error_fields(error),
            }

            print(
                f"失败 [{error.code}]："
                f"{error}"
            )

            records.append(output_record)

            save_records(
                records,
                output_path,
            )

            if stop_on_error:
                raise

            print()
            continue

        success_count += 1

        current_tokens = (
            run.usage.get("total_tokens")
            or 0
        )

        total_tokens += int(
            current_tokens
        )

        total_elapsed_seconds += (
            run.elapsed_seconds
        )

        output_record = {
            **original_fields,
            **build_success_fields(run),
        }

        records.append(output_record)

        save_records(
            records,
            output_path,
        )

        print(
            "成功："
            f"{run.result.overall_sentiment.value}"
        )

        print(
            "维度："
            + ", ".join(
                (
                    f"{aspect.aspect.value}:"
                    f"{aspect.sentiment.value}"
                )
                for aspect in run.result.aspects
            )
        )

        print(
            f"耗时：{run.elapsed_seconds} 秒"
        )
        print(
            f"Token：{current_tokens}"
        )
        print()

    average_elapsed_seconds = (
        total_elapsed_seconds / success_count
        if success_count
        else 0.0
    )

    summary = {
        "total_count": total_count,
        "success_count": success_count,
        "failed_count": failed_count,
        "success_rate": (
            success_count / total_count
        ),
        "average_elapsed_seconds": round(
            average_elapsed_seconds,
            3,
        ),
        "total_tokens": total_tokens,
        "output_path": str(output_path),
    }

    print("=== 批量分析汇总 ===")
    print(
        f"成功：{success_count}/{total_count}"
    )
    print(
        f"失败：{failed_count}/{total_count}"
    )
    print(
        "平均成功请求耗时："
        f"{average_elapsed_seconds:.3f} 秒"
    )
    print(f"总 Token：{total_tokens}")
    print(f"结果文件：{output_path}")

    return summary


def main(
    argv: Sequence[str] | None = None,
) -> int:
    """批量分析命令行入口。"""
    parser = build_parser()
    args = parser.parse_args(argv)

    input_path = args.input.resolve()

    output_path = (
        args.output.resolve()
        if args.output is not None
        else make_default_output_path()
    )

    if not input_path.exists():
        print(
            f"输入文件不存在：{input_path}",
            file=sys.stderr,
        )
        return 2

    try:
        dataframe = pd.read_csv(
            input_path,
            dtype=str,
            keep_default_na=False,
            encoding="utf-8-sig",
        )

        analyzer = FeedbackAnalyzer()

        summary = process_dataframe(
            dataframe,
            analyzer=analyzer,
            output_path=output_path,
            id_column=args.id_column,
            text_column=args.text_column,
            limit=args.limit,
            stop_on_error=(
                args.stop_on_error
            ),
        )
    except FeedbackAnalyzerError as error:
        print(
            f"批量任务停止 [{error.code}]："
            f"{error}",
            file=sys.stderr,
        )
        return 1
    except Exception as error:
        print(
            "批量任务失败："
            f"{type(error).__name__}: "
            f"{error}",
            file=sys.stderr,
        )
        return 2

    return (
        0
        if summary["failed_count"] == 0
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
