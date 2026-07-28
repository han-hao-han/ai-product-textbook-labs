from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lab02_meeting_minutes.src.config import load_settings, validate_real_api_settings
from lab02_meeting_minutes.src.pipeline import run_mock_pipeline, run_real_pipeline
from lab02_meeting_minutes.addon_real_dataset.scripts.qmsum_local_dataset import CACHE_DIR as QMSUM_CACHE_DIR
from lab02_meeting_minutes.addon_real_dataset.scripts.qmsum_local_dataset import dataset_is_downloaded, download_qmsum_dataset, list_qmsum_cases, write_converted_case
from lab02_meeting_minutes.addon_real_dataset.scripts.qmsum_pipeline import run_qmsum_real_pipeline


LAB_DIR = Path(__file__).resolve().parent
DATA_DIR = LAB_DIR / "data"
OUTPUT_DIR = LAB_DIR / "outputs" / "streamlit_runs"
CUSTOM_INPUT_DIR = OUTPUT_DIR / "custom_inputs"
ADDON_DIR = LAB_DIR / "addon_real_dataset"
VERIFIED_REPORT = LAB_DIR / "outputs" / "fixed_regression_real_v11_report.json"
VERIFIED_MAIN = LAB_DIR / "outputs" / "fixed_regression" / "real" / "meeting_main_001.json"


def main() -> None:
    st.set_page_config(page_title="1.5.2 智能会议纪要实验", layout="wide")
    st.title("1.5.2 智能会议纪要与任务提取助手")
    st.caption("H4 冻结候选：查看输入、运行状态、结构化结果、校验结果、模型信息和下载结果。")

    lock = _read_json(LAB_DIR / "experiment_lock.json")

    _render_model_info(lock)

    tab_verified, tab_custom, tab_run, tab_addon, tab_files = st.tabs(["已验证结果", "上传/粘贴分析", "预置样例", "真实数据附加实验", "文件与下载"])
    with tab_verified:
        _render_verified_result()
    with tab_custom:
        _render_custom_run()
    with tab_run:
        _render_preset_run()
    with tab_addon:
        _render_addon_experiment()
    with tab_files:
        _render_downloads()


def _render_model_info(lock: dict[str, Any]) -> None:
    st.markdown(f"**默认模型：** `{lock.get('model')}`")
    st.caption(
        f"Prompt：{lock.get('prompt_version')} | "
        f"Schema：{lock.get('schema_version')} | "
        f"Validator：{lock.get('validator_version')}"
    )


def _render_verified_result() -> None:
    if not VERIFIED_MAIN.exists():
        st.warning("未找到已验证主案例结果。")
        return
    result = _read_json(VERIFIED_MAIN)
    transcript = (DATA_DIR / "main" / "meeting_main_001.md").read_text(encoding="utf-8")
    left, right = st.columns([1, 1])
    with left:
        st.subheader("输入会议转写")
        st.text_area("meeting_main_001", transcript, height=520, disabled=True)
    with right:
        st.subheader("运行状态")
        _render_result_summary(result)
        _render_structured_result(result)


def _render_result_summary(result: dict[str, Any]) -> None:
    metadata = result.get("processing_metadata", {})
    issues = result.get("validation_issues", [])
    cols = st.columns(4)
    cols[0].metric("行动项", len(result.get("action_items", [])))
    cols[1].metric("决策", len(result.get("decisions", [])))
    cols[2].metric("未决问题", len(result.get("open_questions", [])))
    cols[3].metric("校验问题", len(issues))
    if issues:
        st.error("存在校验问题")
        st.json(issues)
    else:
        st.success("结构、证据、日期和负责人校验通过")
    st.write(
        {
            "model": metadata.get("model"),
            "prompt_version": metadata.get("prompt_version"),
            "schema_version": metadata.get("schema_version"),
            "validator_version": metadata.get("validator_version"),
            "mode": metadata.get("mode"),
            "elapsed_seconds": metadata.get("elapsed_seconds"),
        }
    )


def _render_structured_result(result: dict[str, Any], key_prefix: str = "default") -> None:
    st.subheader("结构化结果")
    st.write("行动项")
    st.table(_table(result.get("action_items", []), ["action_id", "task", "owner", "due_date_raw", "due_date_normalized", "evidence"]))
    st.write("决策")
    st.table(_table(result.get("decisions", []), ["decision_id", "decision", "evidence"]))
    st.write("未决问题")
    st.table(_table(result.get("open_questions", []), ["question_id", "question", "owner", "evidence"]))
    meeting_id = str(result.get("meeting_id", "result"))
    safe_key = re.sub(r"[^A-Za-z0-9_-]+", "_", f"{key_prefix}_{meeting_id}")
    st.download_button("下载当前 JSON", _json_bytes(result), file_name=f"{meeting_id}.json", mime="application/json", key=f"download_current_json_{safe_key}")


def _render_custom_run() -> None:
    st.subheader("上传/粘贴分析")
    uploaded = st.file_uploader("上传会议转写文件", type=["md", "txt"])
    pasted = st.text_area("或直接粘贴会议文本", height=320, placeholder="粘贴会议转写文本。建议保留说话人标识，例如：张三：……")
    meeting_id = st.text_input("会议 ID", value="custom_meeting")
    meeting_date = st.text_input("会议日期", value="", placeholder="可选，例如 2026-07-21；没有日期可留空")
    st.caption("上传/粘贴分析只支持真实模型调用，会消耗 1 次 API 预算；不会自动运行，必须点击按钮。")

    if st.button("调用真实模型分析上传/粘贴内容", type="primary"):
        text = _custom_text(uploaded, pasted)
        if not text.strip():
            st.error("请先上传文件或粘贴会议文本。")
            return
        input_path = _write_custom_input(meeting_id, text)
        output_path = OUTPUT_DIR / f"{input_path.stem}_real.json"
        settings = load_settings()
        try:
            validate_real_api_settings(settings)
            result = run_real_pipeline(input_path, output_path, settings, meeting_date=meeting_date.strip() or None, force_mode="single_pass")
        except Exception as exc:  # Streamlit should show actionable error without exposing secrets.
            st.error(str(exc))
            return
        st.success(f"已保存：{output_path}")
        result_payload = result.model_dump(mode="json")
        _render_result_summary(result_payload)
        _render_structured_result(result_payload, key_prefix="custom")


def _render_preset_run() -> None:
    st.subheader("预置样例")
    cases = _case_options()
    case_label = st.selectbox("选择样例", list(cases.keys()), index=0)
    mode = st.radio("运行方式", ["mock", "real"], horizontal=True)
    case = cases[case_label]
    st.caption("real 会消耗真实 API 调用预算；mock 不消耗预算。")
    if st.button("运行所选样例", type="primary"):
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output_path = OUTPUT_DIR / f"{case['id']}_{mode}.json"
        settings = load_settings()
        try:
            if mode == "real":
                validate_real_api_settings(settings)
                result = run_real_pipeline(case["path"], output_path, settings, force_mode="single_pass")
            else:
                result = run_mock_pipeline(case["path"], output_path, settings, force_mode="single_pass")
        except Exception as exc:  # Streamlit should show actionable error without exposing secrets.
            st.error(str(exc))
            return
        st.success(f"已保存：{output_path}")
        _render_result_summary(result.model_dump(mode="json"))
        _render_structured_result(result.model_dump(mode="json"), key_prefix=f"preset_{case['id']}_{mode}")


def _render_addon_experiment() -> None:
    st.subheader("真实数据附加实验")
    if not ADDON_DIR.exists():
        st.warning("未找到附加实验目录。")
        return

    verified = _read_json(ADDON_DIR / "evidence" / "verified_results.json")
    acceptance = _read_json(ADDON_DIR / "outputs" / "addon_acceptance_report.json")
    result = _read_json(ADDON_DIR / "outputs" / "real_smoke" / "TS3010a_v2_result.json")
    gold_compare = _read_json(ADDON_DIR / "outputs" / "real_smoke" / "TS3010a_v2_gold_compare.json")
    transcript_path = ADDON_DIR / "data" / "selected_cases" / "TS3010a.md"

    dataset = verified.get("dataset", {})
    smoke = verified.get("real_smoke_v2", {})
    cols = st.columns(4)
    cols[0].metric("数据集", str(dataset.get("name")))
    cols[1].metric("样例", str(dataset.get("case_id")))
    cols[2].metric("设计要求召回", f"{smoke.get('recalled_decision_count')}/{smoke.get('expected_decision_count')}")
    cols[3].metric("自动验收", "通过" if acceptance.get("ok") else "未通过")

    st.caption("该页展示 QMSum 主样例 TS3010a 的已验证结果；完整数据集入口用于本地探索，不代表完整 QMSum benchmark 性能。")
    left, right = st.columns([1, 1])
    with left:
        st.write("输入样例")
        st.text_area("QMSum Product/val/TS3010a", transcript_path.read_text(encoding="utf-8"), height=420, disabled=True)
    with right:
        st.write("运行状态")
        _render_result_summary(result)
        st.write("金标准对照")
        st.json(
            {
                "ok": gold_compare.get("ok"),
                "expected_decision_count": gold_compare.get("expected_decision_count"),
                "recalled_decision_count": gold_compare.get("recalled_decision_count"),
                "issues": gold_compare.get("issues", []),
            }
        )
    _render_structured_result(result, key_prefix="addon_verified")
    _render_curated_qmsum_samples()
    _render_qmsum_full_dataset_tools()
    st.write("附加实验文件")
    for path, description in _addon_download_files():
        if path.exists():
            st.markdown(f"**{path.name}**")
            st.caption(description)
            st.download_button(f"下载 {path.name}", path.read_bytes(), file_name=path.name, key=f"addon_download_{path.name}")


def _render_curated_qmsum_samples() -> None:
    st.subheader("仓库内保留的 QMSum 样例")
    sample_paths = sorted((ADDON_DIR / "data" / "selected_cases").glob("*.md"))
    if not sample_paths:
        st.warning("未找到仓库内 QMSum 样例。")
        return
    labels = [path.name for path in sample_paths]
    selected = st.selectbox("选择仓库内样例", labels, key="curated_qmsum_sample")
    selected_path = sample_paths[labels.index(selected)]
    st.text_area("样例预览", selected_path.read_text(encoding="utf-8"), height=260, disabled=True, key=f"preview_{selected_path.stem}")
    st.caption("TS3010a 有人工金标准；其他仓库内样例用于探索性结构化分析，不做 gold 验收。")
    if st.button("分析仓库内 QMSum 样例"):
        settings = load_settings()
        output_path = OUTPUT_DIR / f"{selected_path.stem}_real.json"
        try:
            validate_real_api_settings(settings)
            result = run_qmsum_real_pipeline(selected_path, output_path, settings)
        except Exception as exc:
            st.error(str(exc))
            return
        st.success(f"已保存：{output_path}")
        payload = result.model_dump(mode="json")
        _render_result_summary(payload)
        _render_structured_result(payload, key_prefix=f"addon_curated_{selected_path.stem}")


def _render_qmsum_full_dataset_tools() -> None:
    st.subheader("完整 QMSum 数据集")
    st.caption("完整数据集会下载到本地忽略目录，不写入仓库；非 TS3010a 样例没有人工金标准，只做结构化抽取和证据校验。下载约百 MB，请确认网络和磁盘空间。")
    st.write(f"本地缓存目录：`{QMSUM_CACHE_DIR}`")

    if dataset_is_downloaded():
        cases = list_qmsum_cases()
        st.success(f"已检测到本地 QMSum 缓存，可选样例 {len(cases)} 个。")
    else:
        cases = []
        st.warning("尚未检测到完整 QMSum 本地缓存。")

    if st.button("下载完整 QMSum 数据集到本地缓存"):
        try:
            metadata = download_qmsum_dataset()
        except Exception as exc:
            st.error(str(exc))
            return
        st.success(f"下载完成，可选样例 {metadata.get('case_count')} 个。")
        st.json(metadata)
        cases = list_qmsum_cases()

    if not cases:
        return

    labels = [case.label for case in cases]
    selected_label = st.selectbox("从完整 QMSum 数据集中选择样例", labels)
    selected_case = cases[labels.index(selected_label)]
    preview_path = write_converted_case(selected_case, OUTPUT_DIR / "qmsum_selected_inputs")
    preview_text = preview_path.read_text(encoding="utf-8")
    st.text_area("转换后的会议文本预览", preview_text, height=300, disabled=True)
    st.caption("点击分析会调用真实模型并消耗 1 次 API；结果保存到 outputs/streamlit_runs。")
    if st.button("分析所选 QMSum 样例", type="primary"):
        settings = load_settings()
        output_path = OUTPUT_DIR / f"{preview_path.stem}_real.json"
        try:
            validate_real_api_settings(settings)
            result = run_qmsum_real_pipeline(preview_path, output_path, settings)
        except Exception as exc:
            st.error(str(exc))
            return
        st.success(f"已保存：{output_path}")
        payload = result.model_dump(mode="json")
        _render_result_summary(payload)
        _render_structured_result(payload, key_prefix=f"addon_full_{preview_path.stem}")


def _render_downloads() -> None:
    st.subheader("文件与下载")
    files = [
        (
            LAB_DIR / "outputs" / "fixed_regression_real_v11_report.json",
            "代表真实回归汇总，记录少量真实模型样例的通过情况和金标准对照结果。",
        ),
        (
            LAB_DIR / "outputs" / "acceptance_report_h4_final.json",
            "自动验收脚本生成的机器可读报告，用于确认文件、版本、回归、截图和敏感信息检查。",
        ),
        (
            LAB_DIR / "evidence" / "verified_results.json",
            "实验事实包的机器可读摘要，汇总已验证结果、截图、验收和 API 调用计数。",
        ),
        (
            LAB_DIR / "evidence" / "screenshots_manifest.md",
            "截图清单，记录每张截图对应的输入、内容和隐私检查状态。",
        ),
        (
            LAB_DIR / "evidence" / "acceptance_report.md",
            "面向人工复核的 H4 自动验收说明。",
        ),
        (
            LAB_DIR / "evidence" / "h4_final_review.md",
            "H4 阶段过程记录，包含冻结候选、真实回归和预算策略说明。",
        ),
        (
            LAB_DIR / "experiment_lock.json",
            "冻结版本记录，用于复现实验时确认数据、模型、Prompt、Schema 和校验器版本。",
        ),
        (
            LAB_DIR / "api_call_budget.json",
            "真实模型调用计数记录，用于审计本实验已消耗的 API 调用预算。",
        ),
    ]
    st.write("这些文件用于复核实验结果、复现实验环境和交接教材事实材料。")
    for path, description in files:
        if not path.exists():
            st.warning(f"缺少：{path.name}")
            continue
        st.markdown(f"**{path.name}**")
        st.caption(description)
        st.download_button(f"下载 {path.name}", path.read_bytes(), file_name=path.name, key=f"main_download_{path.name}")


def _case_options() -> dict[str, dict[str, Any]]:
    options: dict[str, dict[str, Any]] = {}
    for group in ["main", "demo", "regression", "edge"]:
        for path in sorted((DATA_DIR / group).glob("*.md")):
            options[f"{group}/{path.stem}"] = {"id": path.stem, "path": path}
    return options


def _custom_text(uploaded: Any, pasted: str) -> str:
    if uploaded is not None:
        return uploaded.getvalue().decode("utf-8")
    return pasted


def _write_custom_input(meeting_id: str, text: str) -> Path:
    CUSTOM_INPUT_DIR.mkdir(parents=True, exist_ok=True)
    safe_id = _safe_filename(meeting_id or "custom_meeting")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = CUSTOM_INPUT_DIR / f"{safe_id}_{timestamp}.md"
    content = text if text.lstrip().startswith("# ") else f"# {safe_id}\n\n{text}"
    path.write_text(content, encoding="utf-8")
    return path


def _safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "custom_meeting"


def _addon_download_files() -> list[tuple[Path, str]]:
    return [
        (ADDON_DIR / "outputs" / "real_smoke" / "TS3010a_v2_result.json", "v2 真实模型结构化结果。"),
        (ADDON_DIR / "outputs" / "real_smoke" / "TS3010a_v2_gold_compare.json", "v2 结果与小规模人工金标准的语义对照报告。"),
        (ADDON_DIR / "outputs" / "addon_acceptance_report.json", "附加实验自动验收报告。"),
        (ADDON_DIR / "evidence" / "verified_results.json", "附加实验已验证结果摘要。"),
        (ADDON_DIR / "evidence" / "known_limitations.md", "附加实验已知限制。"),
        (ADDON_DIR / "evidence" / "handoff_summary.md", "附加实验工程交接摘要。"),
    ]


def _table(items: list[dict[str, Any]], columns: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items:
        row = {column: item.get(column) for column in columns}
        if isinstance(row.get("owner"), list):
            row["owner"] = "、".join(row["owner"])
        rows.append(row)
    return rows


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
