from __future__ import annotations

import json
import py_compile
import subprocess
import sys
from pathlib import Path
from typing import Any

import pandas as pd


SCRIPT_PATH = Path(__file__).resolve()
LAB_DIR = SCRIPT_PATH.parents[1]
REPOSITORY_ROOT = SCRIPT_PATH.parents[2]

BATCH_RESULT_PATH = (
    LAB_DIR
    / "expected_outputs"
    / "batch"
    / "deepseek_demo_5_v3.csv"
)

DEMO_DATA_PATH = (
    LAB_DIR
    / "data"
    / "feedback_demo_5.csv"
)

CORE_FILES = [
    LAB_DIR / "src" / "schemas.py",
    LAB_DIR / "src" / "prompts.py",
    LAB_DIR / "src" / "json_parser.py",
    LAB_DIR / "src" / "validators.py",
    LAB_DIR / "src" / "semantic_checks.py",
    LAB_DIR / "src" / "analyzer.py",
    LAB_DIR / "cli.py",
    LAB_DIR / "batch.py",
    LAB_DIR / "app.py",
]

LOCAL_TEST_FILES = [
    LAB_DIR / "tests" / "test_analyzer_local.py",
    LAB_DIR / "tests" / "test_batch_local.py",
]

EXPECTED_REVIEWS: dict[str, dict[str, Any]] = {
    "7688": {
        "overall": {"mixed"},
        "aspects": {
            "service": {"negative", "mixed"},
            "price": {"negative", "mixed"},
        },
    },
    "13222": {
        "overall": {"mixed"},
        "aspects": {
            "price": {"mixed"},
        },
    },
    "2828": {
        "overall": {"negative"},
        "aspects": {},
    },
    "39662": {
        "overall": {"mixed", "negative"},
        "aspects": {
            "price": {"negative"},
            "environment": {"negative"},
        },
    },
    "24593": {
        "overall": {"mixed"},
        "aspects": {
            "food": {"mixed"},
            "environment": {"negative"},
        },
    },
}


def check_required_files() -> None:
    """确认实验所需文件全部存在。"""
    required_files = [
        *CORE_FILES,
        *LOCAL_TEST_FILES,
        DEMO_DATA_PATH,
        BATCH_RESULT_PATH,
    ]

    missing_files = [
        path
        for path in required_files
        if not path.exists()
    ]

    if missing_files:
        formatted = "\n".join(
            f"- {path}"
            for path in missing_files
        )

        raise AssertionError(
            "缺少实验文件：\n"
            f"{formatted}"
        )

    print("REQUIRED_FILES_OK")


def check_python_syntax() -> None:
    """编译核心 Python 文件，检查语法。"""
    for path in CORE_FILES:
        py_compile.compile(
            str(path),
            doraise=True,
        )

    print("PYTHON_SYNTAX_OK")


def run_local_test(
    test_path: Path,
) -> None:
    """运行一个完全本地的 Mock 测试。"""
    completed = subprocess.run(
        [
            sys.executable,
            str(test_path),
        ],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    if completed.stdout:
        print(completed.stdout.strip())

    if completed.returncode != 0:
        if completed.stderr:
            print(
                completed.stderr,
                file=sys.stderr,
            )

        raise AssertionError(
            f"本地测试失败：{test_path.name}"
        )


def check_local_tests() -> None:
    """运行分析器和批处理本地测试。"""
    for test_path in LOCAL_TEST_FILES:
        print()
        print(
            f"正在运行：{test_path.name}"
        )

        run_local_test(test_path)

    print()
    print("ALL_LOCAL_TESTS_OK")


def load_batch_dataframe() -> pd.DataFrame:
    """读取五条真实批量分析结果。"""
    dataframe = pd.read_csv(
        BATCH_RESULT_PATH,
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
    )

    required_columns = {
        "review_id",
        "review_text",
        "analysis_status",
        "overall_sentiment",
        "aspects_json",
        "issue_summary",
        "suggested_action",
        "model_requested",
        "model_returned",
        "prompt_version",
        "elapsed_seconds",
        "total_tokens",
    }

    missing_columns = (
        required_columns
        - set(dataframe.columns)
    )

    if missing_columns:
        raise AssertionError(
            "批量结果缺少字段："
            + ", ".join(
                sorted(missing_columns)
            )
        )

    return dataframe


def parse_aspects(
    raw_value: str,
) -> list[dict[str, str]]:
    """解析 CSV 中的维度 JSON。"""
    try:
        data = json.loads(raw_value)
    except json.JSONDecodeError as error:
        raise AssertionError(
            f"aspects_json 不是合法 JSON：{error}"
        ) from error

    if not isinstance(data, list):
        raise AssertionError(
            "aspects_json 必须是数组"
        )

    return data


def check_single_result(
    row: pd.Series,
) -> None:
    """检查一条批量结果的结构和语义。"""
    review_id = str(
        row["review_id"]
    ).strip()

    review_text = str(
        row["review_text"]
    )

    if review_id not in EXPECTED_REVIEWS:
        raise AssertionError(
            f"出现未知评论 ID：{review_id}"
        )

    if row["analysis_status"] != "success":
        raise AssertionError(
            f"{review_id} 分析状态不是 success"
        )

    if (
        row["model_requested"]
        != "deepseek-v4-flash"
    ):
        raise AssertionError(
            f"{review_id} 请求模型不正确"
        )

    if (
        row["model_returned"]
        != "deepseek-v4-flash"
    ):
        raise AssertionError(
            f"{review_id} 返回模型不正确"
        )

    if (
        row["prompt_version"]
        != "v3_billing_consistency"
    ):
        raise AssertionError(
            f"{review_id} Prompt 版本不正确"
        )

    if not row["issue_summary"].strip():
        raise AssertionError(
            f"{review_id} 缺少问题概括"
        )

    if not row[
        "suggested_action"
    ].strip():
        raise AssertionError(
            f"{review_id} 缺少改进建议"
        )

    try:
        elapsed_seconds = float(
            row["elapsed_seconds"]
        )

        total_tokens = int(
            float(row["total_tokens"])
        )
    except ValueError as error:
        raise AssertionError(
            f"{review_id} 运行统计不是数字"
        ) from error

    if elapsed_seconds <= 0:
        raise AssertionError(
            f"{review_id} 耗时必须大于 0"
        )

    if total_tokens <= 0:
        raise AssertionError(
            f"{review_id} Token 必须大于 0"
        )

    aspects = parse_aspects(
        row["aspects_json"]
    )

    aspect_map: dict[str, str] = {}

    for index, item in enumerate(
        aspects
    ):
        aspect = str(
            item.get("aspect", "")
        )

        sentiment = str(
            item.get("sentiment", "")
        )

        evidence = str(
            item.get("evidence", "")
        )

        if not aspect:
            raise AssertionError(
                f"{review_id} 的第 {index} 个维度为空"
            )

        if aspect in aspect_map:
            raise AssertionError(
                f"{review_id} 出现重复维度：{aspect}"
            )

        aspect_map[aspect] = sentiment

        if not evidence:
            raise AssertionError(
                f"{review_id} 的 {aspect} 证据为空"
            )

        if evidence not in review_text:
            raise AssertionError(
                f"{review_id} 的 {aspect} "
                "证据不是连续原文"
            )

        if any(
            mark in evidence
            for mark in (
                "...",
                "……",
                "…",
            )
        ):
            raise AssertionError(
                f"{review_id} 的 {aspect} "
                "证据包含省略号"
            )

    expectation = (
        EXPECTED_REVIEWS[review_id]
    )

    if (
        row["overall_sentiment"]
        not in expectation["overall"]
    ):
        raise AssertionError(
            f"{review_id} 总体情感不符合预期："
            f"{row['overall_sentiment']}"
        )

    for aspect, accepted_values in (
        expectation["aspects"].items()
    ):
        actual_value = aspect_map.get(
            aspect
        )

        if actual_value is None:
            raise AssertionError(
                f"{review_id} 缺少维度：{aspect}"
            )

        if actual_value not in accepted_values:
            raise AssertionError(
                f"{review_id} 的 {aspect} "
                f"情感不符合预期：{actual_value}"
            )

    print(
        f"REVIEW_{review_id}_OK"
    )


def check_batch_result() -> None:
    """核验五条真实批量结果。"""
    dataframe = load_batch_dataframe()

    if len(dataframe) != 5:
        raise AssertionError(
            "批量结果必须正好包含 5 条记录，"
            f"实际为 {len(dataframe)} 条"
        )

    actual_ids = set(
        dataframe["review_id"]
        .astype(str)
        .str.strip()
    )

    expected_ids = set(
        EXPECTED_REVIEWS
    )

    if actual_ids != expected_ids:
        raise AssertionError(
            "批量评论 ID 不匹配："
            f"实际={sorted(actual_ids)}，"
            f"预期={sorted(expected_ids)}"
        )

    for _, row in dataframe.iterrows():
        check_single_result(row)

    average_elapsed = pd.to_numeric(
        dataframe["elapsed_seconds"]
    ).mean()

    total_tokens = pd.to_numeric(
        dataframe["total_tokens"]
    ).sum()

    print(
        "BATCH_REAL_RESULTS_OK"
    )

    print(
        f"平均耗时："
        f"{average_elapsed:.3f} 秒"
    )

    print(
        f"总 Token："
        f"{int(total_tokens)}"
    )


def check_env_safety() -> None:
    """
    检查 .env 是否受到基本保护。

    只检查文件名和 .gitignore，不读取或打印密钥。
    """
    env_path = REPOSITORY_ROOT / ".env"

    gitignore_path = (
        REPOSITORY_ROOT
        / ".gitignore"
    )

    if not env_path.exists():
        raise AssertionError(
            "项目根目录缺少 .env"
        )

    if not gitignore_path.exists():
        raise AssertionError(
            "项目根目录缺少 .gitignore"
        )

    gitignore_text = (
        gitignore_path.read_text(
            encoding="utf-8",
            errors="replace",
        )
    )

    ignored_entries = {
        line.strip()
        for line in gitignore_text.splitlines()
        if line.strip()
        and not line.strip().startswith("#")
    }

    if (
        ".env" not in ignored_entries
        and "**/.env" not in ignored_entries
        and "*.env" not in ignored_entries
    ):
        raise AssertionError(
            ".gitignore 尚未忽略 .env"
        )

    print("ENV_SAFETY_OK")


def main() -> None:
    print(
        "=== 实验 1.5.1 最终验收 ==="
    )
    print(
        "本脚本不会调用任何大模型 API。"
    )
    print()

    check_required_files()
    check_python_syntax()
    check_local_tests()
    check_batch_result()
    check_env_safety()

    print()
    print(
        "=== 最终验收结果 ==="
    )
    print(
        "FINAL_ACCEPTANCE_OK"
    )


if __name__ == "__main__":
    main()