from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock

import pandas as pd


LAB_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = LAB_DIR.parent

for path in (REPOSITORY_ROOT, LAB_DIR):
    path_text = str(path)

    if path_text not in sys.path:
        sys.path.insert(0, path_text)


from batch import process_dataframe
from src.analyzer import (
    AnalysisRun,
    FeedbackAnalyzerError,
)
from src.schemas import FeedbackAnalysis


def make_success_run(
    review_id: str,
) -> AnalysisRun:
    result = FeedbackAnalysis.model_validate(
        {
            "review_id": review_id,
            "overall_sentiment": "mixed",
            "aspects": [
                {
                    "aspect": "food",
                    "sentiment": "positive",
                    "evidence": "味道很好",
                },
                {
                    "aspect": "service",
                    "sentiment": "negative",
                    "evidence": "服务很差",
                },
            ],
            "issue_summary": "服务较差。",
            "suggested_action": "改善服务。",
        }
    )

    return AnalysisRun(
        result=result,
        raw_content="{}",
        model_requested="test-model",
        model_returned="test-model",
        prompt_version="test-prompt",
        elapsed_seconds=1.25,
        usage={
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
        },
    )


def test_batch_success_and_failure() -> None:
    dataframe = pd.DataFrame(
        [
            {
                "review_id": "test-001",
                "review_text": (
                    "味道很好，但是服务很差"
                ),
            },
            {
                "review_id": "test-002",
                "review_text": "测试失败评论",
            },
        ]
    )

    analyzer = Mock()

    analyzer.analyze.side_effect = [
        make_success_run("test-001"),
        FeedbackAnalyzerError(
            "模拟证据校验失败",
            code="business_validation_failed",
            issues=[
                {
                    "code": "evidence_not_found",
                    "field_path": (
                        "aspects[0].evidence"
                    ),
                    "message": "证据不存在",
                }
            ],
        ),
    ]

    with tempfile.TemporaryDirectory() as directory:
        output_path = (
            Path(directory)
            / "batch_result.csv"
        )

        summary = process_dataframe(
            dataframe,
            analyzer=analyzer,
            output_path=output_path,
        )

        assert output_path.exists()

        output_dataframe = pd.read_csv(
            output_path,
            dtype=str,
            keep_default_na=False,
            encoding="utf-8-sig",
        )

        assert len(output_dataframe) == 2

        first = output_dataframe.iloc[0]
        second = output_dataframe.iloc[1]

        assert (
            first["analysis_status"]
            == "success"
        )

        assert (
            first["overall_sentiment"]
            == "mixed"
        )

        assert (
            first["aspect_signature"]
            == "food:positive|service:negative"
        )

        assert (
            first["total_tokens"]
            == "150"
        )

        assert (
            second["analysis_status"]
            == "failed"
        )

        assert (
            second["analysis_error_code"]
            == "business_validation_failed"
        )

        assert (
            "evidence_not_found"
            in second[
                "analysis_error_issues"
            ]
        )

        assert summary["total_count"] == 2
        assert summary["success_count"] == 1
        assert summary["failed_count"] == 1
        assert summary["total_tokens"] == 150

    print("BATCH_SUCCESS_ROW_OK")
    print("BATCH_FAILURE_ROW_OK")
    print("BATCH_PROGRESS_SAVE_OK")
    print("BATCH_SUMMARY_OK")


def test_missing_columns() -> None:
    dataframe = pd.DataFrame(
        [
            {
                "wrong_id": "1",
                "wrong_text": "测试",
            }
        ]
    )

    analyzer = Mock()

    with tempfile.TemporaryDirectory() as directory:
        output_path = (
            Path(directory)
            / "missing.csv"
        )

        try:
            process_dataframe(
                dataframe,
                analyzer=analyzer,
                output_path=output_path,
            )
        except ValueError as error:
            assert "缺少必要字段" in str(
                error
            )
        else:
            raise AssertionError(
                "缺少字段时应抛出异常"
            )

    print("MISSING_COLUMNS_REJECTED")


def main() -> None:
    test_batch_success_and_failure()
    test_missing_columns()

    print("BATCH_LOCAL_TESTS_OK")


if __name__ == "__main__":
    main()