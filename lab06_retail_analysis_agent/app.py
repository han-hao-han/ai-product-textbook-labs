"""Streamlit entry for experiment 1.5.6 reader experience and H4 review."""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from src.conversation_state import EffectiveConditions
from src.h4_streamlit_service import (
    H4ServiceError,
    MODEL_ID,
    TOOL_LABELS,
    OnlineTurnExperience,
    build_download_zip,
    build_real_registry,
    build_session_record,
    load_reader_contracts,
    mode_policy,
    run_chat_turn,
    run_manual_tool,
    run_online_turn,
)
from src.run_record import SessionRunRecord, validate_record_security
from src.user_answer_presenter import build_user_answer


PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT.parent / ".env", override=False)
load_dotenv(PROJECT_ROOT / ".env", override=False)

st.set_page_config(
    page_title="1.5.6 零售经营分析 Agent",
    page_icon="🧭",
    layout="wide",
)


@st.cache_resource(show_spinner=False)
def _registry():
    return build_real_registry()


def _new_session_id() -> str:
    return "SESSION-ui-" + datetime.now().strftime("%Y%m%dT%H%M%S%f")


def _initialize_state() -> None:
    defaults: dict[str, Any] = {
        "session_id": _new_session_id(),
        "turn_counter": 0,
        "online_turns": [],
        "fixed_turns": [],
        "chat_messages": [],
        "pending_chat": None,
        "effective_conditions": EffectiveConditions.empty(),
        "last_online": None,
        "last_fixed": None,
        "last_offline": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _reset_session() -> None:
    st.session_state.session_id = _new_session_id()
    st.session_state.turn_counter = 0
    st.session_state.online_turns = []
    st.session_state.fixed_turns = []
    st.session_state.chat_messages = []
    st.session_state.pending_chat = None
    st.session_state.effective_conditions = EffectiveConditions.empty()
    st.session_state.last_online = None
    st.session_state.last_fixed = None
    st.session_state.last_offline = None


def _next_turn_id() -> str:
    st.session_state.turn_counter += 1
    return f"TURN-{st.session_state.turn_counter:03d}"


def _period_arguments(prefix: str) -> dict[str, Any]:
    period = st.selectbox(
        "时间范围",
        ["all_data", "complete_months_only", "custom"],
        format_func={
            "all_data": "全部数据",
            "complete_months_only": "仅完整月份（排除2011-12）",
            "custom": "自定义日期",
        }.get,
        key=f"{prefix}_period",
    )
    start_date = end_date = None
    if period == "custom":
        left, right = st.columns(2)
        with left:
            start = st.date_input(
                "开始日期", value=date(2011, 1, 1), key=f"{prefix}_start"
            )
        with right:
            end = st.date_input(
                "结束日期", value=date(2011, 11, 30), key=f"{prefix}_end"
            )
        start_date, end_date = start.isoformat(), end.isoformat()
    return {"period": period, "start_date": start_date, "end_date": end_date}


def _manual_arguments(tool_name: str) -> dict[str, Any]:
    if tool_name == "get_data_profile":
        return {
            "section": st.selectbox(
                "概况部分",
                ["all", "summary", "classification", "customer_coverage"],
                key="manual_profile_section",
            )
        }
    args = _period_arguments(f"manual_{tool_name}")
    if tool_name == "get_sales_overview":
        args["include_incomplete_period_warning"] = st.checkbox(
            "显示不完整期间提醒", value=True
        )
    elif tool_name in {"rank_products", "analyze_regions"}:
        args["metric"] = st.selectbox(
            "排名指标",
            ["sales_amount", "sales_quantity", "order_count"],
            key=f"manual_{tool_name}_metric",
        )
        args["top_n"] = st.slider(
            "Top N", min_value=1, max_value=10, value=5,
            key=f"manual_{tool_name}_topn",
        )
        if tool_name == "analyze_regions":
            excluded = st.text_input(
                "排除国家或地区（留空表示不排除）",
                value="United Kingdom",
                key="manual_region_excluded",
            ).strip()
            args["excluded_country"] = excluded or None
    elif tool_name == "analyze_time_trend":
        args["grain"] = "month"
        args["metric"] = st.selectbox(
            "趋势指标",
            ["sales_amount", "sales_quantity", "order_count", "average_order_value"],
            key="manual_trend_metric",
        )
        args["exclude_incomplete_periods"] = st.checkbox(
            "排除不完整期间", value=True
        )
    elif tool_name == "analyze_customers":
        args["include_coverage"] = True
    elif tool_name == "compare_segments":
        args["comparison"] = "united_kingdom_vs_other"
    return args


def _fact_rows(facts) -> list[dict[str, Any]]:
    return [
        {
            "FACT": fact.fact_id,
            "来源CALL": fact.call_id,
            "指标": fact.metric,
            "显示值": fact.display_value,
            "单位": fact.unit,
            "排名": fact.rank,
            "维度": "；".join(
                f"{item.name}={item.value}" for item in fact.dimensions
            ),
            "工具": fact.source_tool,
        }
        for fact in facts
    ]


def _render_chart(chart, *, show_provenance: bool = True) -> None:
    values = [float(item) for item in chart.series[0].values]
    frame = pd.DataFrame(
        {chart.series[0].name: values}, index=chart.categories
    )
    if show_provenance:
        st.caption(
            f"{chart.chart_id} · 来源 {chart.call_id} · "
            f"{len(chart.source_fact_ids)} 条 FACT · 单位 {chart.unit}"
        )
    else:
        st.caption(f"单位：{chart.unit}")
    if chart.chart_type == "monthly_line":
        st.line_chart(frame)
    else:
        st.bar_chart(frame, horizontal=chart.chart_type == "top_n_horizontal_bar")


def _render_tool_calls(outcome) -> None:
    if not outcome.tool_calls:
        st.info("本轮没有执行工具。澄清与正确拒答在调用工具前结束属于预期行为。")
        return
    for call in outcome.tool_calls:
        with st.container(border=True):
            st.markdown(f"**{call.call_id} · `{call.tool_name}`**")
            st.caption("模型选择工具 → 程序校验名称和参数 Schema → Pandas 执行")
            st.json(call.arguments, expanded=True)
            st.success(f"执行成功，生成 {len(call.facts)} 条 FACT")
            with st.expander("查看结构化工具结果"):
                st.json(call.result, expanded=False)


def _render_online_result(item: OnlineTurnExperience) -> None:
    outcome = item.outcome
    labels = {
        "completed": "报告完成",
        "needs_clarification": "需要一次集中澄清",
        "boundary": "正确触发能力边界",
        "failed": "本轮失败",
    }
    st.subheader(f"当前轮结果：{labels[outcome.status]}")
    a, b, c = st.columns(3)
    a.metric("模型响应", f"{item.response_attempted}/{item.response_limit}")
    b.metric("工具调用", len(outcome.tool_calls))
    c.metric("FACT", len(outcome.facts))
    if outcome.status == "failed":
        st.error(f"失败阶段：{outcome.error_stage or '未知'}\n\n{outcome.error_message}")
    elif outcome.clarification is not None:
        st.warning(outcome.clarification.message)
        st.write("集中澄清主题：", "、".join(outcome.clarification.topics))
    elif outcome.boundary is not None:
        st.warning(outcome.boundary.message)
        st.write("缺少或不支持：", "、".join(outcome.boundary.missing_fields))
        st.info("可支持的替代分析：" + outcome.boundary.supported_alternative)
    _render_tool_calls(outcome)
    if outcome.facts:
        st.markdown("#### FACT 事实")
        st.dataframe(_fact_rows(outcome.facts), width="stretch", hide_index=True)
    if outcome.charts:
        st.markdown("#### 图表（与 FACT 共用同一份工具数据）")
        for chart in outcome.charts:
            st.markdown(f"**{chart.title}**")
            _render_chart(chart)
    if outcome.report_markdown:
        st.markdown("#### 当前轮经营报告")
        st.markdown(outcome.report_markdown)
    if outcome.report_validation is not None:
        with st.expander("程序报告校验"):
            st.success("正式报告验证器通过")
            st.write("确定性检查：", outcome.report_validation.deterministic_checks)
            st.write("人工审阅章节：", outcome.report_validation.manual_review_required_sections)
    with st.expander("模型原始响应与运输审计（本地调试）"):
        st.caption("原始响应不是主要结果；其中不含 API Key 或请求头。")
        st.json(list(outcome.raw_responses), expanded=False)
        st.json(item.transport_audit, expanded=False)


def _render_chat_answer(item: OnlineTurnExperience) -> None:
    """Render the user-facing answer first and keep engineering evidence folded."""

    outcome = item.outcome
    if outcome.status == "needs_clarification" and outcome.clarification is not None:
        st.markdown(outcome.clarification.message)
        st.caption("请直接在下方输入框一次补充这些条件。")
        return
    if outcome.status == "boundary" and outcome.boundary is not None:
        st.markdown(outcome.boundary.message)
        st.info("可以改为：" + outcome.boundary.supported_alternative)
        with st.expander("为什么当前不能回答"):
            st.write("缺少或不支持：", "、".join(outcome.boundary.missing_fields))
            if outcome.boundary.boundary_codes:
                st.write("边界代码：", outcome.boundary.boundary_codes)
        return
    if outcome.status == "failed":
        st.error("这次分析没有完成。")
        with st.expander("查看失败信息"):
            st.write("阶段：", outcome.error_stage or "未知")
            st.write(outcome.error_message or "没有更多错误信息。")
        return

    answer = build_user_answer(outcome.tool_calls)
    for direct in answer.direct_answers:
        st.markdown(direct)
    if answer.key_points:
        st.markdown("#### 关键数据")
        for point in answer.key_points:
            st.markdown(f"- {point}")
    for table in answer.tables:
        st.markdown(f"#### {table.title}")
        st.dataframe(list(table.rows), width="stretch", hide_index=True)
    for note in answer.notes:
        st.caption(f"口径说明：{note}")
    if outcome.charts:
        for chart in outcome.charts:
            st.markdown(f"**{chart.title}**")
            _render_chart(chart, show_provenance=False)
    with st.expander("查看分析依据：工具、参数、FACT 与程序校验"):
        a, b, c = st.columns(3)
        a.metric("模型响应", f"{item.response_attempted}/{item.response_limit}")
        b.metric("工具调用", len(outcome.tool_calls))
        c.metric("FACT", len(outcome.facts))
        _render_tool_calls(outcome)
        if outcome.facts:
            st.dataframe(
                _fact_rows(outcome.facts), width="stretch", hide_index=True
            )
        if outcome.report_validation is not None:
            if outcome.report_validation.status == "passed":
                st.success("正式报告验证器通过")
            else:
                st.error("正式报告验证器未通过")
            if outcome.report_validation.issues:
                st.json(
                    [
                        issue.model_dump(mode="json")
                        for issue in outcome.report_validation.issues
                    ]
                )
        if outcome.report_markdown:
            st.markdown("##### 内部受控报告（仅供追溯）")
            st.caption(
                "其中的 FACT、REQUEST 和 POLICY 编号用于程序验收，不是面向用户的回答。"
            )
            st.code(outcome.report_markdown, language="markdown")


def _render_offline_result(item) -> None:
    st.subheader("工具层体验结果")
    st.info("本次没有调用模型：工具由你手动选择，不能称为 Agent 自主选择。")
    st.json(item.result, expanded=False)
    st.dataframe(_fact_rows(item.facts), width="stretch", hide_index=True)
    if item.chart is not None:
        _render_chart(item.chart)


def _render_data_contract(metric_contract: dict[str, Any]) -> None:
    baseline = metric_contract["real_data_baseline_after_keep_first"]
    classes = baseline["classes"]
    source_rows = 541909
    valid = classes["sale"]["rows"]
    exceptions = sum(value["rows"] for key, value in classes.items() if key != "sale")
    cols = st.columns(5)
    cols[0].metric("原始记录", f"{source_rows:,}")
    cols[1].metric("正常销售", f"{valid:,}")
    cols[2].metric("异常/非销售", f"{exceptions:,}")
    cols[3].metric("去除完全重复", "5,268")
    cols[4].metric("货币单位", "GBP")
    st.caption("数据时间：2010-12-01 08:26 至 2011-12-09 12:50；2011-12 为不完整期间。")
    st.markdown("#### 冻结清洗规则")
    st.write(
        "原始工作簿保持不变；八字段完全重复只保留首条用于分析；"
        "正常销售要求发票号不以 C 开头、数量大于 0、单价大于 0。"
    )
    class_rows = [
        {"分类": name, "记录数": value["rows"], "订单数": value["unique_invoices"]}
        for name, value in classes.items()
    ]
    st.dataframe(class_rows, width="stretch", hide_index=True)
    st.markdown("#### 冻结指标口径")
    metric_rows = [
        {"指标": name, "事实层": value["scope"], "公式": value["formula"], "单位": value["unit"]}
        for name, value in metric_contract["metrics"].items()
    ]
    st.dataframe(metric_rows, width="stretch", hide_index=True)
    st.warning(
        "数据不含成本、利润、库存和未来观测，因此不支持利润分析、销售预测或自动补货。"
    )


_initialize_state()
metric_contract, questions = load_reader_contracts()
api_key = os.getenv("LLM_API_KEY", "")
policy = mode_policy(api_key)

st.title("1.5.6 基于真实零售数据的经营分析 Agent")
st.caption(
    "模型负责理解问题和选择工具；Pydantic 校验参数；Pandas 精确计算；"
    "程序生成 FACT、图表并校验报告。"
)

with st.sidebar:
    st.header("运行模式")
    if api_key:
        mode = st.radio("选择体验", ["在线Agent", "工具层体验"], horizontal=False)
        st.success("模型服务已配置")
    else:
        mode = "工具层体验"
        st.warning("模型服务未配置")
    st.caption(f"默认在线模型：{MODEL_ID}")
    st.divider()
    st.write("当前会话", st.session_state.session_id.replace("SESSION-ui-", ""))
    st.write("已完成轮次", len(st.session_state.online_turns))
    if st.button("开始新会话", width="stretch"):
        _reset_session()
        st.rerun()
    st.caption("页面不会显示 API Key 的任何字符。")

chat_tab, data_tab, validation_tab, records_tab = st.tabs(
    ["💬 对话分析", "📊 数据与口径", "🧪 教学验收", "📦 运行记录"]
)

with chat_tab:
    if mode == "工具层体验":
        st.header("无在线模型：手动白名单工具")
        st.info(
            "这里可检查真实 Pandas 计算、FACT 和图表，但不包含自然语言理解、"
            "模型选工具、多工具自主调用或 AI 报告。"
        )
        tool_name = st.selectbox(
            "选择一个白名单工具",
            list(TOOL_LABELS),
            format_func=lambda name: f"{TOOL_LABELS[name]}（{name}）",
        )
        manual_args = _manual_arguments(tool_name)
        if st.button("运行所选工具", type="primary"):
            try:
                with st.spinner("正在读取固定数据并执行确定性计算……"):
                    result = run_manual_tool(
                        registry=_registry(),
                        session_id=st.session_state.session_id,
                        turn_id=_next_turn_id(),
                        tool_name=tool_name,
                        arguments=manual_args,
                    )
                st.session_state.last_offline = result
            except Exception as exc:
                st.error(f"工具执行失败：{exc}")
        if st.session_state.last_offline is not None:
            _render_offline_result(st.session_state.last_offline)
    else:
        st.subheader("零售经营分析助手")
        st.caption(
            "可以自由提问或补充上一轮条件。支持销售、商品、地区、时间和客户聚合分析；"
            "不支持上传另一套数据、利润、预测或自动补货。"
            "工具与模型响应额度按单次问题重置，不在整个会话累计。"
        )
        if not st.session_state.chat_messages:
            with st.chat_message("assistant"):
                st.markdown(
                    "你好，我会选择受限的分析工具，并由 Pandas 计算结果。你可以问：\n\n"
                    "- 完整月份中销售额最高的是哪个月？\n"
                    "- 按销售额列出前 5 个商品。\n"
                    "- 比较英国与其他地区的销售表现。"
                )
        for message in st.session_state.chat_messages:
            with st.chat_message(message["role"]):
                if message["role"] == "user":
                    st.markdown(message["content"])
                elif "error" in message:
                    st.error(message["error"])
                else:
                    _render_chat_answer(message["item"])

        if st.session_state.online_turns:
            with st.expander("当前会话有效条件"):
                st.json(
                    st.session_state.effective_conditions.model_dump(mode="json")
                )
                st.caption("历史 FACT 不会直接进入新一轮报告；需要比较时必须重新调用工具。")

        pending = st.session_state.pending_chat
        placeholder = (
            "请一次补充时间范围、指标和比较对象……"
            if pending is not None
            else "输入经营分析问题，或继续补充上一轮条件……"
        )
        user_text = st.chat_input(placeholder)
        if user_text:
            st.session_state.chat_messages.append(
                {"role": "user", "content": user_text}
            )
            try:
                with st.spinner("正在选择白名单工具并核验结果……"):
                    if pending is None:
                        turn_id = _next_turn_id()
                        item = run_chat_turn(
                            api_key=api_key,
                            registry=_registry(),
                            session_id=st.session_state.session_id,
                            turn_id=turn_id,
                            question=user_text,
                            previous_conditions=st.session_state.effective_conditions,
                            inherit_previous=bool(st.session_state.online_turns),
                        )
                    else:
                        item = run_chat_turn(
                            api_key=api_key,
                            registry=_registry(),
                            session_id=st.session_state.session_id,
                            turn_id=pending.outcome.turn_id,
                            question=pending.displayed_question,
                            previous_conditions=st.session_state.effective_conditions,
                            inherit_previous=bool(st.session_state.online_turns),
                            clarification_answer=user_text,
                            pending_experience=pending,
                        )
                st.session_state.chat_messages.append(
                    {"role": "assistant", "item": item}
                )
                st.session_state.last_online = item
                if item.outcome.status == "needs_clarification":
                    st.session_state.pending_chat = item
                else:
                    st.session_state.pending_chat = None
                    st.session_state.online_turns.append(item)
                    st.session_state.effective_conditions = (
                        item.condition_resolution.effective
                    )
                st.rerun()
            except Exception as exc:
                st.session_state.chat_messages.append(
                    {
                        "role": "assistant",
                        "error": f"这次分析没有完成：{exc}",
                    }
                )
                st.rerun()

with data_tab:
    st.header("检查点 1：真实数据与统一口径")
    _render_data_contract(metric_contract)

with validation_tab:
    st.header("教学验收：Q01–Q10 固定问题")
    st.caption(
        "这里是独立 Harness，不控制聊天运行时。顺序：先运行 → 查看证据 → "
        "程序检查 → 再展开参考答案。"
    )
    question_id = st.selectbox(
        "选择固定问题",
        list(questions),
        format_func=lambda qid: f"{qid} · {questions[qid]['type']} · {questions[qid]['question']}",
        key="fixed_question_selector",
    )
    st.markdown(questions[question_id]["question"])
    if st.button(
        "运行并核验当前固定问题",
        type="primary",
        disabled=not bool(api_key),
    ):
        try:
            with st.spinner("正在运行固定问题 Harness……"):
                fixed_item = run_online_turn(
                    api_key=api_key,
                    registry=_registry(),
                    session_id=st.session_state.session_id,
                    turn_id=_next_turn_id(),
                    displayed_question=questions[question_id]["question"],
                    previous_conditions=EffectiveConditions.empty(),
                    inherit_previous=False,
                    question_id=question_id,
                )
            st.session_state.fixed_turns.append(fixed_item)
            st.session_state.last_fixed = fixed_item
        except Exception as exc:
            st.error(f"固定问题运行失败：{exc}")
    if not api_key:
        st.warning("模型服务未配置，固定问题在线验收按钮已禁用。")
    latest_by_id = {
        item.question_id: item
        for item in st.session_state.fixed_turns
        if item.question_id is not None and item.validation is not None
    }
    st.dataframe(
        [
            {
                "题号": qid,
                "类型": question["type"],
                "运行状态": (
                    latest_by_id[qid].outcome.status if qid in latest_by_id else "未运行"
                ),
                "程序核验": (
                    latest_by_id[qid].validation.status if qid in latest_by_id else "待运行"
                ),
                "人工复核": "待用户确认" if qid in latest_by_id else "待运行",
            }
            for qid, question in questions.items()
        ],
        width="stretch",
        hide_index=True,
    )
    completed = len(latest_by_id)
    st.progress(completed / 10, text=f"已完成程序核验 {completed}/10；这不是综合智能分数。")
    if st.session_state.last_fixed is not None:
        _render_online_result(st.session_state.last_fixed)
    inspect_id = st.selectbox("查看已运行问题的核验依据", list(questions), key="validation_view")
    if inspect_id not in latest_by_id:
        st.warning("该题尚未在本会话运行，因此暂不展示参考答案。")
    else:
        validation = latest_by_id[inspect_id].validation
        if validation.status == "passed_deterministic_pending_manual_review":
            st.success("协议、数据流和确定性结果通过；仍需人工判断表达质量。")
        else:
            st.error("程序核验未通过。")
        if validation.issues:
            st.dataframe(
                [issue.model_dump(mode="json") for issue in validation.issues],
                width="stretch",
            )
        with st.expander("运行后解锁：人工标注参考结果"):
            st.json(questions[inspect_id]["reference_answer"])
        with st.expander("人工检查清单"):
            for check in questions[inspect_id]["manual_checklist"]:
                st.checkbox(check, key=f"manual_{inspect_id}_{check}")

with records_tab:
    st.header("运行记录、显式导出与导入查看")
    if st.session_state.online_turns:
        try:
            record = build_session_record(st.session_state.online_turns)
            archive = build_download_zip(record, st.session_state.online_turns[-1].outcome.turn_id)
            st.download_button(
                "下载当前会话证据包（ZIP）",
                data=archive,
                file_name="retail_agent_run_bundle.zip",
                mime="application/zip",
            )
            st.caption(
                "包含运行记录、FACT、图表数据；当前轮有正式报告时同时包含 Markdown 报告。"
            )
            with st.expander("当前运行记录摘要"):
                st.json(record.model_dump(mode="json"), expanded=False)
        except Exception as exc:
            st.error(f"当前会话暂不能导出：{exc}")
    else:
        st.info("在线 Agent 至少完成一轮后才能导出会话证据包。")
    uploaded = st.file_uploader("导入已有 run_record.json（只查看，不执行模型）", type=["json"])
    if uploaded is not None:
        try:
            imported = SessionRunRecord.model_validate_json(uploaded.getvalue())
            validate_record_security(imported)
            st.success(f"导入通过：{len(imported.turns)} 个轮次；未调用模型。")
            st.dataframe(
                [
                    {
                        "轮次": turn.turn_id,
                        "问题": turn.original_question,
                        "工具数": len(turn.tool_calls),
                        "FACT数": len(turn.facts),
                        "有报告": turn.report_markdown is not None,
                    }
                    for turn in imported.turns
                ],
                width="stretch",
                hide_index=True,
            )
        except Exception as exc:
            st.error(f"导入被拒绝：{exc}")

st.divider()
st.caption(
    "隐私边界：原始 CustomerID 只可在本地用于确定性聚合；页面和导出只展示客户聚合指标。"
)
