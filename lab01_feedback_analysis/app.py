from __future__ import annotations

import io
import sys
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st


LAB_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = LAB_DIR.parent

for path in (REPOSITORY_ROOT, LAB_DIR):
    path_text = str(path)

    if path_text not in sys.path:
        sys.path.insert(0, path_text)


from batch import process_dataframe
from src.analyzer import (
    AnalysisRun,
    FeedbackAnalyzer,
    FeedbackAnalyzerError,
)


DEMO_DATA_PATH = (
    LAB_DIR
    / "data"
    / "feedback_demo_5.csv"
)

SENTIMENT_LABELS = {
    "positive": "正面",
    "neutral": "中性",
    "negative": "负面",
    "mixed": "褒贬混合",
}

ASPECT_LABELS = {
    "location": "位置",
    "service": "服务",
    "price": "价格",
    "environment": "环境",
    "food": "菜品",
}


def initialize_state() -> None:
    """初始化单条分析和批量分析的会话状态。"""
    default_values = {
        "analysis_run": None,
        "analysis_error": None,
        "batch_result_dataframe": None,
        "batch_summary": None,
        "batch_csv_bytes": None,
        "batch_error": None,
    }

    for key, value in default_values.items():
        if key not in st.session_state:
            st.session_state[key] = value


@st.cache_resource
def get_analyzer() -> FeedbackAnalyzer:
    """创建并缓存大模型分析器。"""
    return FeedbackAnalyzer()


def sentiment_text(value: str) -> str:
    """返回中英文情感标签。"""
    chinese = SENTIMENT_LABELS.get(
        value,
        value,
    )

    return f"{chinese}（{value}）"


def aspect_text(value: str) -> str:
    """返回中英文维度标签。"""
    chinese = ASPECT_LABELS.get(
        value,
        value,
    )

    return f"{chinese}（{value}）"


def render_error(
    error: FeedbackAnalyzerError,
) -> None:
    """展示单条分析错误。"""
    st.error(
        f"分析失败：{error}"
    )

    st.caption(
        f"错误代码：{error.code}"
    )

    if error.issues:
        with st.expander(
            "查看具体错误",
            expanded=True,
        ):
            for issue in error.issues:
                issue_code = (
                    issue.get("code")
                    or issue.get("error_type")
                    or "unknown_error"
                )

                field_path = issue.get(
                    "field_path",
                    "",
                )

                message = issue.get(
                    "message",
                    "",
                )

                st.markdown(
                    (
                        f"- `{issue_code}` "
                        f"**{field_path}**："
                        f"{message}"
                    )
                )


def build_aspect_dataframe(
    run: AnalysisRun,
) -> pd.DataFrame:
    """将维度结果转换成页面表格。"""
    rows: list[dict[str, Any]] = []

    for item in run.result.aspects:
        rows.append(
            {
                "评价维度": aspect_text(
                    item.aspect.value
                ),
                "情感判断": sentiment_text(
                    item.sentiment.value
                ),
                "原文证据": item.evidence,
            }
        )

    return pd.DataFrame(rows)


def render_single_result(
    run: AnalysisRun,
) -> None:
    """展示单条评论分析结果。"""
    result = run.result

    st.success(
        "分析完成，结果已通过结构和原文证据校验。"
    )

    first_column, second_column = (
        st.columns(2)
    )

    with first_column:
        st.metric(
            "评论 ID",
            result.review_id,
        )

    with second_column:
        st.metric(
            "总体情感",
            sentiment_text(
                result.overall_sentiment.value
            ),
        )

    st.subheader("评价维度与原文证据")

    aspect_dataframe = (
        build_aspect_dataframe(run)
    )

    if aspect_dataframe.empty:
        st.info(
            "没有识别到明确的评价维度。"
        )
    else:
        st.dataframe(
            aspect_dataframe,
            use_container_width=True,
            hide_index=True,
        )

    st.subheader("问题概括")

    if result.issue_summary:
        st.write(result.issue_summary)
    else:
        st.info(
            "评论中没有明确需要改进的问题。"
        )

    st.subheader("改进建议")

    if result.suggested_action:
        st.write(
            result.suggested_action
        )
    else:
        st.info(
            "当前没有生成改进建议。"
        )

    with st.expander(
        "运行信息",
        expanded=False,
    ):
        metadata_dataframe = pd.DataFrame(
            [
                {
                    "请求模型": (
                        run.model_requested
                    ),
                    "返回模型": (
                        run.model_returned
                    ),
                    "Prompt 版本": (
                        run.prompt_version
                    ),
                    "耗时（秒）": (
                        run.elapsed_seconds
                    ),
                    "输入 Token": (
                        run.usage.get(
                            "prompt_tokens"
                        )
                    ),
                    "输出 Token": (
                        run.usage.get(
                            "completion_tokens"
                        )
                    ),
                    "总 Token": (
                        run.usage.get(
                            "total_tokens"
                        )
                    ),
                }
            ]
        )

        st.dataframe(
            metadata_dataframe,
            use_container_width=True,
            hide_index=True,
        )

        st.caption(
            "只有通过 Schema、连续原文证据和业务规则校验的结果才会显示。"
        )


def render_single_tab() -> None:
    """渲染单条评论分析标签页。"""
    st.subheader("单条评论分析")

    st.write(
        "输入一条真实餐饮评论，系统将完成总体情感分析、"
        "评价维度识别、原文证据提取和改进建议生成。"
    )

    review_id = st.text_input(
        "评论 ID",
        placeholder="例如：7688",
        help="用于唯一标识当前评论。",
        key="single_review_id",
    )

    review_text = st.text_area(
        "评论内容",
        height=240,
        placeholder=(
            "请粘贴一条真实的餐饮用户评论……"
        ),
        help=(
            "模型提取的每条证据必须是输入文本中的连续原文。"
        ),
        key="single_review_text",
    )

    analyze_button = st.button(
        "开始分析",
        type="primary",
        use_container_width=True,
        key="single_analyze_button",
    )

    if analyze_button:
        normalized_review_id = (
            review_id.strip()
        )

        normalized_review_text = (
            review_text.strip()
        )

        if not normalized_review_id:
            st.warning(
                "请先输入评论 ID。"
            )
        elif not normalized_review_text:
            st.warning(
                "请先输入评论内容。"
            )
        else:
            st.session_state.analysis_run = None
            st.session_state.analysis_error = None

            try:
                analyzer = get_analyzer()

                with st.spinner(
                    "正在调用模型并校验分析结果……"
                ):
                    run = analyzer.analyze(
                        review_id=(
                            normalized_review_id
                        ),
                        review_text=(
                            normalized_review_text
                        ),
                    )
            except FeedbackAnalyzerError as error:
                st.session_state.analysis_error = (
                    error
                )
            except Exception as error:
                st.session_state.analysis_error = (
                    FeedbackAnalyzerError(
                        (
                            "发生未预期错误："
                            f"{type(error).__name__}: "
                            f"{error}"
                        ),
                        code="unexpected_error",
                    )
                )
            else:
                st.session_state.analysis_run = run

    analysis_error = (
        st.session_state.analysis_error
    )

    analysis_run = (
        st.session_state.analysis_run
    )

    if analysis_error is not None:
        st.divider()
        render_error(analysis_error)

    if analysis_run is not None:
        st.divider()
        render_single_result(analysis_run)


def read_uploaded_csv(
    uploaded_file: Any,
) -> pd.DataFrame:
    """读取用户上传的 CSV，兼容常见中文编码。"""
    file_bytes = uploaded_file.getvalue()

    encoding_errors: list[str] = []

    for encoding in (
        "utf-8-sig",
        "utf-8",
        "gb18030",
    ):
        try:
            return pd.read_csv(
                io.BytesIO(file_bytes),
                dtype=str,
                keep_default_na=False,
                encoding=encoding,
            )
        except UnicodeDecodeError:
            encoding_errors.append(
                encoding
            )

    raise ValueError(
        "无法识别 CSV 编码，已尝试："
        + ", ".join(encoding_errors)
    )


def load_builtin_demo() -> pd.DataFrame:
    """读取固定的五条真实演示数据。"""
    if not DEMO_DATA_PATH.exists():
        raise FileNotFoundError(
            f"缺少内置演示数据：{DEMO_DATA_PATH}"
        )

    return pd.read_csv(
        DEMO_DATA_PATH,
        dtype=str,
        keep_default_na=False,
        encoding="utf-8-sig",
    )


def render_batch_summary() -> None:
    """展示已经完成的批量分析结果。"""
    summary = (
        st.session_state.batch_summary
    )

    result_dataframe = (
        st.session_state
        .batch_result_dataframe
    )

    csv_bytes = (
        st.session_state.batch_csv_bytes
    )

    if (
        summary is None
        or result_dataframe is None
    ):
        return

    st.success(
        "批量分析完成，结果已逐条保存并通过基础校验。"
    )

    columns = st.columns(4)

    with columns[0]:
        st.metric(
            "总数",
            summary["total_count"],
        )

    with columns[1]:
        st.metric(
            "成功",
            summary["success_count"],
        )

    with columns[2]:
        st.metric(
            "失败",
            summary["failed_count"],
        )

    with columns[3]:
        st.metric(
            "平均耗时",
            (
                f"{summary['average_elapsed_seconds']}"
                " 秒"
            ),
        )

    st.subheader("批量分析结果")

    preferred_columns = [
        "review_id",
        "analysis_status",
        "overall_sentiment",
        "aspect_signature",
        "issue_summary",
        "suggested_action",
        "elapsed_seconds",
        "total_tokens",
    ]

    visible_columns = [
        column
        for column in preferred_columns
        if column in result_dataframe.columns
    ]

    st.dataframe(
        result_dataframe[
            visible_columns
        ],
        use_container_width=True,
        hide_index=True,
    )

    if csv_bytes is not None:
        st.download_button(
            "下载完整分析结果 CSV",
            data=csv_bytes,
            file_name=(
                "feedback_batch_streamlit.csv"
            ),
            mime="text/csv",
            use_container_width=True,
        )

    with st.expander(
        "查看完整字段",
        expanded=False,
    ):
        st.dataframe(
            result_dataframe,
            use_container_width=True,
            hide_index=True,
        )


def render_batch_tab() -> None:
    """渲染批量 CSV 分析标签页。"""
    st.subheader("批量 CSV 分析")

    st.write(
        "上传包含 review_id 和 review_text 字段的 CSV，"
        "或使用实验固定的五条真实评论演示集。"
    )

    data_source = st.radio(
        "数据来源",
        options=[
            "使用内置五条演示数据",
            "上传 CSV 文件",
        ],
        horizontal=True,
        key="batch_data_source",
    )

    dataframe: pd.DataFrame | None = None

    try:
        if (
            data_source
            == "使用内置五条演示数据"
        ):
            dataframe = load_builtin_demo()
        else:
            uploaded_file = st.file_uploader(
                "选择 CSV 文件",
                type=["csv"],
                key="batch_file_uploader",
            )

            if uploaded_file is not None:
                dataframe = read_uploaded_csv(
                    uploaded_file
                )
    except Exception as error:
        st.error(
            "数据读取失败："
            f"{type(error).__name__}: "
            f"{error}"
        )

    if dataframe is None:
        st.info(
            "请选择数据后再执行批量分析。"
        )
        return

    st.caption(
        f"当前数据共 {len(dataframe)} 条。"
    )

    st.dataframe(
        dataframe.head(10),
        use_container_width=True,
        hide_index=True,
    )

    if dataframe.empty:
        st.warning(
            "当前 CSV 没有可处理的数据。"
        )
        return

    maximum_count = len(dataframe)

    process_count = st.number_input(
        "处理条数",
        min_value=1,
        max_value=maximum_count,
        value=maximum_count,
        step=1,
        help=(
            "截图和正式演示建议处理全部五条固定数据。"
        ),
        key="batch_process_count",
    )

    start_button = st.button(
        "开始批量分析",
        type="primary",
        use_container_width=True,
        key="batch_start_button",
    )

    if start_button:
        st.session_state.batch_result_dataframe = None
        st.session_state.batch_summary = None
        st.session_state.batch_csv_bytes = None
        st.session_state.batch_error = None

        try:
            analyzer = get_analyzer()

            with st.spinner(
                (
                    f"正在分析 {int(process_count)} 条评论，"
                    "请勿关闭页面……"
                )
            ):
                with tempfile.TemporaryDirectory() as directory:
                    output_path = (
                        Path(directory)
                        / "streamlit_batch_result.csv"
                    )

                    summary = process_dataframe(
                        dataframe,
                        analyzer=analyzer,
                        output_path=output_path,
                        limit=int(process_count),
                    )

                    result_dataframe = pd.read_csv(
                        output_path,
                        dtype=str,
                        keep_default_na=False,
                        encoding="utf-8-sig",
                    )

                    csv_bytes = (
                        output_path.read_bytes()
                    )
        except Exception as error:
            st.session_state.batch_error = (
                f"{type(error).__name__}: {error}"
            )
        else:
            st.session_state.batch_summary = (
                summary
            )

            st.session_state[
                "batch_result_dataframe"
            ] = result_dataframe

            st.session_state[
                "batch_csv_bytes"
            ] = csv_bytes

    batch_error = (
        st.session_state.batch_error
    )

    if batch_error:
        st.error(
            f"批量分析失败：{batch_error}"
        )

    if (
        st.session_state.batch_summary
        is not None
    ):
        st.divider()
        render_batch_summary()


def main() -> None:
    """Streamlit 应用入口。"""
    st.set_page_config(
        page_title="用户反馈智能分析助手",
        page_icon="💬",
        layout="wide",
    )

    initialize_state()

    st.title("用户反馈智能分析助手")

    st.write(
        "基于大模型 API 完成餐饮用户反馈的结构化分析，"
        "支持单条输入和 CSV 批量处理。"
    )

    st.caption(
        "当前默认模型：DeepSeek V4 Flash；"
        "Prompt：v3_billing_consistency。"
    )

    st.divider()

    single_tab, batch_tab = st.tabs(
        [
            "单条分析",
            "批量分析",
        ]
    )

    with single_tab:
        render_single_tab()

    with batch_tab:
        render_batch_tab()


if __name__ == "__main__":
    main()