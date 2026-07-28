from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import streamlit as st


PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.generation_client import read_generation_state  # noqa: E402
from src.checkpoint3_report import (  # noqa: E402
    EXPERIENCE_TYPES,
    build_checkpoint3_report,
)
from src.interactive_save import save_interactive_result  # noqa: E402
from src.io_utils import read_json  # noqa: E402
from src.paths import RUNS_DIR  # noqa: E402
from src.rag_pipeline import run_rag_query  # noqa: E402


st.set_page_config(
    page_title="FastAPI中文文档RAG",
    page_icon="📚",
    layout="wide",
)


def _available_runs() -> list[str]:
    if not RUNS_DIR.is_dir():
        return []
    return sorted(
        (
            path.name
            for path in RUNS_DIR.iterdir()
            if path.is_dir() and (path / "manifest.json").is_file()
        ),
        reverse=True,
    )


def _section_text(value: Any) -> str:
    if isinstance(value, list):
        return " > ".join(str(item) for item in value)
    return str(value)


def _render_phase_table(result: dict[str, Any]) -> None:
    rows = []
    for phase in result["phases"]:
        rows.append(
            {
                "阶段": phase["name"],
                "状态": phase["status"],
                "耗时（秒）": phase.get("elapsed_seconds"),
            }
        )
    st.dataframe(rows, width="stretch", hide_index=True)


def _render_retrieval(result: dict[str, Any]) -> None:
    retrieval = result.get("retrieval")
    if not retrieval:
        return
    cited = {
        item["chunk_id"]
        for item in result.get("citations", [])
    }
    st.subheader("Top-k检索过程")
    for hit in retrieval["hits"]:
        is_cited = (
            result["final_state"] == "answered"
            and hit["chunk_id"] in cited
        )
        label = (
            f"Top {hit['rank']} · {hit['score']:.4f} · "
            f"{hit['page_title']}"
        )
        if is_cited:
            label += " · 已引用"
        with st.expander(label, expanded=is_cited):
            st.caption(
                f"{_section_text(hit['section_path'])} · "
                f"{hit['source_path']} · {hit['chunk_id']}"
            )
            st.markdown(hit["content"], unsafe_allow_html=False)


def _render_final(result: dict[str, Any]) -> None:
    final_state = result["final_state"]
    st.subheader("最终状态")
    if final_state == "answered":
        st.success("answered：回答和引用均通过程序校验")
        st.markdown(
            result["answer"]["answer"],
            unsafe_allow_html=False,
        )
    elif final_state == "model_refused":
        st.warning("model_refused：模型判断Top-k证据不足")
        st.write(result["answer"]["refusal_reason"])
    elif final_state == "retrieval_rejected":
        st.warning("retrieval_rejected：Top 1低于正式阈值，未调用在线模型")
    elif final_state == "retrieval_only":
        st.info(
            "retrieval_only：检索和门控已完成；生成客户端尚未通过准备，"
            "或当前环境及lab04_fastapi_rag/.env中没有DASHSCOPE_API_KEY。"
        )
    elif final_state == "validation_failed":
        st.error("validation_failed：模型响应未通过结构、引用或安全校验")
        st.write(result.get("generation", {}).get("error", "未知校验错误"))
    else:
        st.error("generation_failed：在线生成调用失败")
        st.write(result.get("generation", {}).get("error", "未知生成错误"))
    for warning in result.get("validation_warnings", []):
        st.warning(warning)

    if result.get("citations"):
        st.subheader("程序生成的参考依据")
        for citation in result["citations"]:
            st.markdown(
                f"**{citation['page_title']}**  \n"
                f"{_section_text(citation['section_path'])}  \n"
                f"[固定Commit来源]({citation['source_url']}) · "
                f"`{citation['chunk_id']}`",
                unsafe_allow_html=False,
            )
            st.code(citation["excerpt"], language=None)
            st.caption(
                f"连续摘录位置：{citation['start_offset']}～"
                f"{citation['end_offset']}；"
                f"{citation['visible_characters']}字符"
            )


def _render_evaluation_report(
    run_dir: Path,
    report: dict[str, Any],
) -> None:
    evaluation = report["evaluation"]
    metrics = report["metrics"]
    judge = report["judge"]

    st.subheader("正式评价概览")
    columns = st.columns(4)
    columns[0].metric(
        "正式题",
        f"{evaluation['completed_count']}/{evaluation['question_count']}",
    )
    columns[1].metric(
        "Top 1合理命中率",
        f"{metrics['retrieval']['top1_reasonable_hit_rate']:.1%}",
    )
    columns[2].metric(
        "可接受回答率",
        f"{metrics['answers']['acceptable_answer_rate']:.1%}",
    )
    columns[3].metric(
        "正确拒答",
        (
            f"{metrics['boundary_refusal']['correct_refusals'] + metrics['out_of_scope_refusal']['correct_refusals']}"
            f"/{metrics['boundary_refusal']['denominator'] + metrics['out_of_scope_refusal']['denominator']}"
        ),
    )
    if report["status"] == "passed":
        st.success("检查点4状态：passed")
    else:
        st.warning(
            f"检查点4状态：{report['status']}。请结合失败终态和逐题结果判断，"
            "warning不代表流程未完成。"
        )

    st.subheader("检索、分类与回答")
    st.dataframe(
        [
            {
                "指标": "Top 1合理命中",
                "结果": (
                    f"{metrics['retrieval']['top1_single_source_hits']}/"
                    f"{metrics['retrieval']['top1_single_source_denominator']}"
                ),
                "比率": f"{metrics['retrieval']['top1_reasonable_hit_rate']:.1%}",
            },
            {
                "指标": "Top 5来源完整命中",
                "结果": (
                    f"{metrics['retrieval']['top5_full_hits']}/"
                    f"{metrics['retrieval']['top5_denominator']}"
                ),
                "比率": f"{metrics['retrieval']['top5_source_hit_rate']:.1%}",
            },
            {
                "指标": "分类严格正确",
                "结果": (
                    f"{metrics['classification']['strict_correct']}/"
                    f"{metrics['classification']['denominator']}"
                ),
                "比率": f"{metrics['classification']['strict_accuracy']:.1%}",
            },
            {
                "指标": "回答完全正确",
                "结果": (
                    f"{metrics['answers']['grade_distribution']['fully_correct']}/"
                    f"{metrics['answers']['formal_in_scope_denominator']}"
                ),
                "比率": f"{metrics['answers']['fully_correct_rate']:.1%}",
            },
            {
                "指标": "回答可接受",
                "结果": (
                    f"{metrics['answers']['judged_answer_count']}/"
                    f"{metrics['answers']['formal_in_scope_denominator']}"
                ),
                "比率": f"{metrics['answers']['acceptable_answer_rate']:.1%}",
            },
        ],
        width="stretch",
        hide_index=True,
    )

    st.subheader("拒答与机制")
    st.dataframe(
        [
            {
                "范围": "边界题",
                "正确拒答": (
                    f"{metrics['boundary_refusal']['correct_refusals']}/"
                    f"{metrics['boundary_refusal']['denominator']}"
                ),
                "机制符合": (
                    f"{metrics['boundary_refusal']['mechanism_conforming']}/"
                    f"{metrics['boundary_refusal']['denominator']}"
                ),
            },
            {
                "范围": "知识库外",
                "正确拒答": (
                    f"{metrics['out_of_scope_refusal']['correct_refusals']}/"
                    f"{metrics['out_of_scope_refusal']['denominator']}"
                ),
                "机制符合": (
                    f"{metrics['out_of_scope_refusal']['mechanism_conforming']}/"
                    f"{metrics['out_of_scope_refusal']['denominator']}"
                ),
            },
        ],
        width="stretch",
        hide_index=True,
    )

    evaluation_summary_path = run_dir / "evaluation" / "summary.json"
    judge_summary_path = run_dir / "judge" / "formal" / "summary.json"
    if evaluation_summary_path.is_file() and judge_summary_path.is_file():
        evaluation_summary = read_json(evaluation_summary_path)
        judge_summary = read_json(judge_summary_path)
        grades = {
            item["question_id"]: item.get("answer_grade")
            for item in judge_summary["records"]
        }
        rows = []
        for item in evaluation_summary["records"]:
            comparison = item["program_comparison"]
            rows.append(
                {
                    "题目ID": item["question_id"],
                    "范围": item["scope"],
                    "最终状态": item["final_state"],
                    "Top 1合理命中": comparison["retrieval"][
                        "top1_reasonable_hit"
                    ],
                    "Top 5来源": comparison["retrieval"][
                        "top5_source_status"
                    ],
                    "分类严格正确": comparison["classification"][
                        "strict_correct"
                    ],
                    "拒答正确": comparison["refusal"]["refusal_correct"],
                    "Judge等级": grades.get(item["question_id"]),
                }
            )
        st.subheader("30题首次正式结果")
        st.dataframe(rows, width="stretch", hide_index=True)

    st.caption(
        f"Judge：{judge['model']} / reasoning={judge['reasoning_effort']} / "
        f"CLI {judge['cli_version']}；语义等级仅来自独立attempt_001。"
    )
    st.download_button(
        "下载检查点4报告JSON",
        data=json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        file_name="checkpoint_4_report.json",
        mime="application/json",
        key=f"download_checkpoint_4_{run_dir.name}",
    )


st.title("基于RAG的FastAPI中文文档问答助手")
st.caption(
    "固定FastAPI 0.136.3文档、Qwen3本地Embedding、NumPy精确检索、"
    "Top 1门控和百炼结构化回答。每次问题独立，不使用聊天历史。"
)

runs = _available_runs()
if not runs:
    st.error("未找到实验运行。请先运行 scripts/init_experiment_run.py。")
    st.stop()

selected_run = st.sidebar.selectbox("实验运行", runs)
run_dir = RUNS_DIR / selected_run
generation_state = read_generation_state(run_dir)
st.sidebar.metric("生成客户端状态", generation_state["status"])
st.sidebar.caption(
    "API Key从当前环境或lab04_fastapi_rag/.env读取，"
    "不在页面中输入或写入结果。"
)

tab_index, tab_qa, tab_evaluation = st.tabs(
    ["文档与索引", "问答与检索过程", "正式验证结果"]
)

with tab_index:
    try:
        source = read_json(run_dir / "source" / "document_manifest.json")
        corpus = read_json(run_dir / "corpus" / "corpus_manifest.json")
        index = read_json(
            run_dir / "index" / "current" / "index_manifest.json"
        )
        model = read_json(run_dir / "model" / "embedding_model.json")
        included_documents = int(source["included_markdown_files"])
        if included_documents != int(corpus["document_count"]):
            raise ValueError(
                "document_manifest与corpus_manifest的文档数量不一致"
            )
        columns = st.columns(4)
        columns[0].metric("中文文档", included_documents)
        columns[1].metric("Chunk", corpus["chunk_count"])
        columns[2].metric("向量维度", index["dimension"])
        columns[3].metric("索引行数", index["matrix_shape"][0])
        st.write(
            {
                "FastAPI Commit": source["commit"],
                "语料SHA-256": corpus["corpus_sha256"],
                "Embedding模型": model["model_id"],
                "Embedding Revision": model["revision"],
                "设备": model["device"],
                "索引SHA-256": index["embeddings_sha256"],
                "正式门控阈值": 0.6831968426704407,
            }
        )
        st.info(
            "Streamlit只加载并核验已有索引，不提供下载、建库或自动修复按钮。"
        )
    except (FileNotFoundError, KeyError, OSError, ValueError) as error:
        st.error(
            f"索引前置产物不可用：{type(error).__name__}: {error}"
        )
        st.code(
            f"python scripts/build_index.py --experiment-run-id {selected_run}"
        )

with tab_qa:
    if "rag_history" not in st.session_state:
        st.session_state.rag_history = []
    question = st.text_area(
        "输入一个独立问题",
        max_chars=2000,
        height=130,
        placeholder="例如：如何使用Pydantic模型声明请求体？",
    )
    top_k = st.slider("探索Top k", min_value=3, max_value=8, value=5)
    if st.button("运行检索与问答", type="primary"):
        try:
            with st.spinner("正在执行查询Embedding、检索、门控与必要的生成…"):
                result = run_rag_query(
                    run_dir,
                    question,
                    top_k=top_k,
                )
            st.session_state.rag_history.insert(0, result)
            st.session_state.rag_history = st.session_state.rag_history[:10]
        except (
            FileNotFoundError,
            ImportError,
            KeyError,
            OSError,
            RuntimeError,
            TypeError,
            ValueError,
        ) as error:
            st.error(f"运行失败：{type(error).__name__}: {error}")

    if st.session_state.rag_history:
        current = st.session_state.rag_history[0]
        st.caption(
            f"问题：{current['question']} · "
            f"总耗时：{current['total_elapsed_seconds']}秒"
        )
        _render_phase_table(current)
        _render_final(current)
        _render_retrieval(current)
        st.divider()
        experience_type = st.selectbox(
            "这条结果用于哪类读者体验？",
            options=list(EXPERIENCE_TYPES),
            format_func=lambda value: EXPERIENCE_TYPES[value],
            key=f"experience_type_{current['created_at']}",
        )
        confirmed = st.checkbox(
            "我确认将当前结果保存到本地运行目录",
            key=f"save_confirm_{current['created_at']}",
        )
        if st.button(
            "保存当前结果",
            disabled=not confirmed,
            key=f"save_button_{current['created_at']}",
        ):
            try:
                current["reader_experience_type"] = experience_type
                saved = save_interactive_result(
                    run_dir,
                    current,
                    confirmed=confirmed,
                )
                st.success(
                    f"已保存：{saved.relative_to(run_dir).as_posix()}"
                )
            except (OSError, TypeError, ValueError) as error:
                st.error(f"保存失败：{type(error).__name__}: {error}")
        st.caption(
            f"会话内保留最近{len(st.session_state.rag_history)}条结果；"
            "历史结果不参与下一次检索或生成。"
        )
        st.download_button(
            "下载当前校验后结果JSON",
            data=json.dumps(current, ensure_ascii=False, indent=2) + "\n",
            file_name="rag_result.json",
            mime="application/json",
            key=f"download_result_{current['created_at']}",
        )
        st.divider()
        st.write(
            "分别保存一条知识库内、边界和知识库外结果后，可以生成检查点3报告。"
        )
        if st.button("生成检查点3报告"):
            try:
                report_md, _ = build_checkpoint3_report(run_dir)
                st.success(
                    f"已生成：{report_md.relative_to(run_dir).as_posix()}"
                )
            except (
                FileExistsError,
                FileNotFoundError,
                KeyError,
                OSError,
                TypeError,
                ValueError,
            ) as error:
                st.error(
                    f"检查点3报告未生成：{type(error).__name__}: {error}"
                )

with tab_evaluation:
    report_path = (
        run_dir / "checkpoints" / "checkpoint_4" / "report.json"
    )
    if report_path.is_file():
        report = read_json(report_path)
        _render_evaluation_report(run_dir, report)
    else:
        st.info(
            "正式验证尚未运行。检查点3人工确认前不得运行30道正式题。"
        )
        st.code(
            f"python scripts/run_evaluation.py --experiment-run-id "
            f"{selected_run}"
        )
