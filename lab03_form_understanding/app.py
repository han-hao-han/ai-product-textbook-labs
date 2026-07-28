from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import streamlit as st

from src.model_client import OpenAICompatibleVisionClient
from src.paths import LOCAL_DATA_DIR, PROJECT_ROOT, RESULTS_DIR, split_paths
from src.result_store import safe_error_message
from src.sample_service import (
    find_document,
    run_builtin_sample,
    run_custom_sample,
)
from src.session_logic import should_start_real_run, stored_result_for_input
from src.settings import (
    load_model_candidate,
    load_model_settings,
    require_h3_frozen,
)
from src.subset_config import load_teaching_subset
from src.upload_validator import UploadValidationError, save_validated_upload, validate_uploaded_image
from src.validation_runner import run_fixed_validation
from src.xfund_loader import load_xfund_documents, resolve_image_path


DIFFICULTY_LABELS = {"simple": "简单", "medium": "中等", "complex": "较复杂"}
FINAL_STATUS_LABELS = {
    "exact_match": "完全匹配",
    "normalized_match": "规范化后匹配",
    "wrong_value": "值错误",
    "key_value_mismatch": "键值错配",
    "missing": "遗漏",
    "extra": "额外字段",
    "manual_review": "人工复核",
}
DATASET_STATUS_LABELS = {
    "exact_match": "完全一致",
    "normalized_match": "规范化后一致",
    "different_value": "值不一致",
    "different_pairing": "配对不一致",
    "not_in_model_output": "模型输出中未找到",
    "not_in_dataset_annotation": "数据集原始标注中未找到",
}
DIAGNOSTIC_LABELS = {
    "reference_value_contained_in_model_value": "数据集值包含于模型值",
    "model_value_contained_in_reference_value": "模型值包含于数据集值",
    "same_value_different_key": "同值异键",
    "checkbox_symbol_difference": "复选符号差异",
    "same_key_multiple_dataset_values_combined": "同键多行可能被模型合并",
    "high_key_similarity": "字段名高度相似",
    "high_value_similarity": "字段值高度相似",
}
CUSTOM_NOTICE = "当前输入没有人工标注参考结果，系统只能检查输出结构，不能自动判断内容是否正确。"


@st.cache_resource
def load_app_context() -> dict[str, Any]:
    candidate = load_model_candidate()
    try:
        require_h3_frozen(candidate)
        h3_ready = True
        h3_block_reason = None
    except ValueError as error:
        h3_ready = False
        h3_block_reason = str(error)
    subset = load_teaching_subset(PROJECT_ROOT / "configs" / "teaching_subset.json")
    annotation_path, images_dir = split_paths("train")
    documents = load_xfund_documents(annotation_path)
    return {
        "candidate": candidate,
        "h3_ready": h3_ready,
        "h3_block_reason": h3_block_reason,
        "subset": subset,
        "annotation_path": annotation_path,
        "images_dir": images_dir,
        "documents": documents,
    }


def json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def format_accuracy(value: float | None) -> str:
    return "不适用" if value is None else f"{value:.2%}"


def render_summary(summary: dict[str, Any]) -> None:
    columns = st.columns(4)
    columns[0].metric("参考字段", summary["reference_field_count"])
    columns[1].metric("完全匹配", summary["exact_match"])
    columns[2].metric("规范化匹配", summary["normalized_match"])
    columns[3].metric(
        "参考字段识别正确率",
        format_accuracy(summary["reference_field_recognition_accuracy"]),
    )
    st.dataframe(
        [
            {"状态": "值错误", "数量": summary["wrong_value"]},
            {"状态": "键值错配", "数量": summary["key_value_mismatch"]},
            {"状态": "遗漏", "数量": summary["missing"]},
            {"状态": "额外字段", "数量": summary["extra"]},
            {"状态": "人工复核", "数量": summary["manual_review"]},
        ],
        hide_index=True,
        width="stretch",
    )


def render_dataset_summary(summary: dict[str, Any]) -> None:
    columns = st.columns(4)
    columns[0].metric(
        "数据集原始标注字段", summary["dataset_annotation_field_count"]
    )
    columns[1].metric("完全一致", summary["exact_match"])
    columns[2].metric("规范化后一致", summary["normalized_match"])
    columns[3].metric(
        "数据集原始标注一致率",
        format_accuracy(summary["dataset_annotation_consistency_rate"]),
    )
    st.dataframe(
        [
            {"状态": "值不一致", "数量": summary["different_value"]},
            {"状态": "配对不一致", "数量": summary["different_pairing"]},
            {
                "状态": "模型输出中未找到",
                "数量": summary["not_in_model_output"],
            },
            {
                "状态": "数据集原始标注中未找到",
                "数量": summary["not_in_dataset_annotation"],
            },
        ],
        hide_index=True,
        width="stretch",
    )
    st.caption(
        "该一致率只描述模型输出与XFUND原始标注是否相同，不代表模型正确率。"
    )


def render_single_result(record: dict[str, Any]) -> None:
    if record.get("error"):
        st.error(record["error"])
        return
    payload = record["payload"]
    st.success("真实模型调用、JSON解析和Schema v1校验成功。字段内容仍需比较或人工判断。")
    columns = st.columns(4)
    columns[0].metric("模型", payload["model"])
    columns[1].metric("耗时", f"{payload['elapsed_seconds']}秒")
    columns[2].metric("fields", len(payload["result"]["fields"]))
    columns[3].metric("warnings", len(payload["result"]["warnings"]))

    st.subheader("结构化字段")
    if payload["result"]["fields"]:
        st.dataframe(payload["result"]["fields"], hide_index=True, width="stretch")
    else:
        st.info("模型没有返回字段。")
    st.subheader("warnings")
    if payload["result"]["warnings"]:
        for warning in payload["result"]["warnings"]:
            st.warning(warning)
    else:
        st.caption("无warning。")
    with st.expander("模型原始响应"):
        st.code(payload["raw_response"], language="json")

    if payload["input_type"] == "custom":
        st.warning(CUSTOM_NOTICE)
    else:
        st.subheader("XFUND原始标注字段")
        st.caption(
            "这些字段来自数据集显式question-answer关系；在人工复核前不视为正确答案。"
        )
        reference_rows = [
            {"字段名": row["key"], "字段值": row["value"]}
            for row in payload["reference"]["reference_fields"]
        ]
        st.dataframe(reference_rows, hide_index=True, width="stretch")

        comparison = payload["comparison"]["dataset_annotation_comparison"]
        st.subheader("第一层：与数据集原始标注逐字段比较")
        comparison_rows = [
            {
                "状态": DATASET_STATUS_LABELS[row["status"]],
                "数据集字段": row["dataset_key"],
                "数据集值": row["dataset_value"],
                "模型字段": row["model_key"],
                "模型值": row["model_value"],
                "诊断提示": "、".join(
                    DIAGNOSTIC_LABELS[hint]
                    for hint in row["diagnostic_hints"]
                ),
            }
            for row in comparison["dataset_annotation_results"]
        ]
        comparison_rows.extend(
            {
                "状态": "数据集原始标注中未找到",
                "数据集字段": None,
                "数据集值": None,
                "模型字段": row["model_key"],
                "模型值": row["model_value"],
                "诊断提示": "、".join(
                    DIAGNOSTIC_LABELS[hint]
                    for hint in row["diagnostic_hints"]
                ),
            }
            for row in comparison["model_only_fields"]
        )
        st.dataframe(comparison_rows, hide_index=True, width="stretch")
        if comparison["diagnostic_links"]:
            with st.expander("查看跨字段诊断链接（不自动判对）"):
                st.dataframe(
                    [
                        {
                            "数据集字段序号": "、".join(
                                str(index + 1)
                                for index in link[
                                    "dataset_annotation_indices"
                                ]
                            ),
                            "模型字段序号": "、".join(
                                str(index + 1)
                                for index in link["model_indices"]
                            ),
                            "提示": "、".join(
                                DIAGNOSTIC_LABELS[hint]
                                for hint in link["diagnostic_hints"]
                            ),
                            "字段名相似度": link["similarity_scores"][
                                "key_similarity"
                            ],
                            "字段值相似度": link["similarity_scores"][
                                "value_similarity"
                            ],
                        }
                        for link in comparison["diagnostic_links"]
                    ],
                    hide_index=True,
                    width="stretch",
                )
        st.subheader("第一层汇总")
        render_dataset_summary(comparison["summary"])

        st.subheader("第二层：人工复核后的最终参考结果")
        final_reference = payload["comparison"]["final_reference"]
        st.write(f"复核状态：`{final_reference['status']}`")
        evaluation_context = final_reference.get("evaluation_context")
        if (
            isinstance(evaluation_context, dict)
            and evaluation_context.get("usage")
            == "teaching_post_run_adjudication_only"
        ):
            st.info(
                "该最终参考结果是在模型运行后由人工结合原图裁决，"
                "仅用于主样本教学展示，不纳入正式固定验证统计。"
            )
        final_comparison = payload["comparison"]["final_reference_comparison"]
        if final_comparison is None:
            st.warning(
                "当前样本的最终参考结果尚未由人工确认或校正，"
                "因此不计算“参考字段识别正确率”。"
            )
        else:
            final_rows = [
                {
                    "状态": FINAL_STATUS_LABELS[row["status"]],
                    "最终参考字段": row["key"],
                    "最终参考值": row["value"],
                    "模型字段": row["predicted_key"],
                    "模型值": row["predicted_value"],
                    "参考来源": row["reference_origin"],
                }
                for row in final_comparison["reference_results"]
            ]
            final_rows.extend(
                {
                    "状态": "额外字段",
                    "最终参考字段": None,
                    "最终参考值": None,
                    "模型字段": row["key"],
                    "模型值": row["value"],
                    "参考来源": None,
                }
                for row in final_comparison["extra_fields"]
            )
            st.dataframe(final_rows, hide_index=True, width="stretch")
            render_summary(final_comparison["summary"])

    st.caption("本地生成文件（相对实验目录）")
    st.json(payload["files"])
    st.download_button(
        "下载本次JSON",
        data=json_bytes(payload),
        file_name=f"{payload['sample_id']}_{payload['model_run_id']}.json",
        mime="application/json",
        key=f"download_single_{payload['model_run_id']}",
    )


def builtin_options(subset: dict) -> list[tuple[str, str]]:
    role_labels = {
        "many_fields": "观察样本1（字段较多）",
        "long_key_value_distance": "观察样本2（键值距离较远）",
        "complex_layout": "观察样本3（布局较复杂）",
    }
    options = [("教材主样本", subset["main"]["sample_id"])]
    options.extend(
        (role_labels[item["role"]], item["sample_id"])
        for item in subset["observations"]
    )
    return options


def render_single_tab(context: dict[str, Any]) -> None:
    st.header("单张表单识别")
    st.caption("选择内置真实样本或上传图片。只有点击并确认后才会调用模型。")
    if not context["h3_ready"]:
        st.warning(
            "H3比较规则v2已实现，但最终参考结果仍在人工复核；"
            "当前页面只读，正式模型调用已禁用。"
        )
    options = builtin_options(context["subset"])
    labels = [f"{label}｜{sample_id}" for label, sample_id in options] + ["上传自定义图片"]
    selected_label = st.selectbox("输入来源", labels)
    is_custom = selected_label == "上传自定义图片"
    image_display: str | bytes | None = None
    input_id: str | None = None
    sample_id: str | None = None
    document = None
    upload_data: bytes | None = None

    if is_custom:
        uploaded = st.file_uploader("上传JPEG、PNG或WebP图片（最大10MB）", type=["jpg", "jpeg", "png", "webp"])
        st.warning(CUSTOM_NOTICE)
        if uploaded is not None:
            upload_data = uploaded.getvalue()
            try:
                validate_uploaded_image(upload_data)
                input_id = f"upload:{hashlib.sha256(upload_data).hexdigest()}"
                image_display = upload_data
            except UploadValidationError as error:
                st.error(str(error))
    else:
        selected_index = labels.index(selected_label)
        sample_id = options[selected_index][1]
        document = find_document(context["documents"], sample_id)
        image_path = resolve_image_path(context["images_dir"], document)
        input_id = f"builtin:{sample_id}"
        image_display = str(image_path)
        st.caption(f"样本ID：{sample_id}")

    if image_display is not None:
        st.image(image_display, caption="当前表单图片", width="stretch")

    confirmed = st.checkbox(
        "我确认本次点击会产生1次真实模型调用",
        key="single_confirm",
        disabled=not context["h3_ready"],
    )
    clicked = st.button(
        "运行单张识别",
        type="primary",
        disabled=(
            not context["h3_ready"]
            or input_id is None
            or st.session_state.get("single_running", False)
        ),
    )
    if clicked and not confirmed:
        st.warning("请先勾选调用确认。")
    if should_start_real_run(
        button_clicked=clicked,
        confirmation_checked=confirmed,
        currently_running=st.session_state.get("single_running", False),
    ):
        st.session_state["single_running"] = True
        settings = None
        try:
            with st.spinner("正在调用固定视觉模型并校验结果……"):
                require_h3_frozen(context["candidate"])
                settings = load_model_settings()
                client = OpenAICompatibleVisionClient(settings)
                if is_custom:
                    assert upload_data is not None
                    custom_id, upload_path = save_validated_upload(
                        upload_data, LOCAL_DATA_DIR / "uploads"
                    )
                    payload = run_custom_sample(
                        sample_id=custom_id,
                        image_path=upload_path,
                        client=client,
                        results_dir=RESULTS_DIR,
                        project_root=PROJECT_ROOT,
                        secrets=(settings.api_key,),
                    )
                else:
                    assert sample_id is not None and document is not None
                    payload = run_builtin_sample(
                        sample_id=sample_id,
                        document=document,
                        images_dir=context["images_dir"],
                        client=client,
                        results_dir=RESULTS_DIR,
                        project_root=PROJECT_ROOT,
                        secrets=(settings.api_key,),
                    )
                st.session_state["single_result"] = {
                    "input_id": input_id,
                    "payload": payload,
                }
        except Exception as error:
            secrets = (settings.api_key,) if settings is not None else ()
            st.session_state["single_result"] = {
                "input_id": input_id,
                "error": f"{type(error).__name__}: {safe_error_message(error, secrets)}",
            }
        finally:
            st.session_state["single_running"] = False

    stored = stored_result_for_input(
        st.session_state.get("single_result"), input_id or ""
    )
    if stored:
        render_single_result(stored)


def render_validation_result(record: dict[str, Any]) -> None:
    if record.get("error"):
        st.error(record["error"])
        return
    outcome = record["outcome"]
    payload = outcome["payload"]
    if payload["complete"]:
        st.success("本次固定验证完整：6张样本均成功。")
    else:
        st.error("本次固定验证不完整：存在失败样本，失败未被静默删除。")
    columns = st.columns(3)
    columns[0].metric("成功样本", payload["successful_sample_count"])
    columns[1].metric("失败样本", payload["failed_sample_count"])
    columns[2].metric("验证完整", "是" if payload["complete"] else "否")

    sample_rows = []
    for sample in payload["samples"]:
        row = {
            "顺序": sample["validation_order"],
            "样本": sample["sample_id"],
            "难度": DIFFICULTY_LABELS[sample["difficulty_group"]],
            "状态": "成功" if sample["status"] == "success" else "失败",
        }
        if sample["status"] == "success":
            row["识别字段数"] = sample["field_count"]
            row["warnings数"] = sample["warning_count"]
            row["耗时（秒）"] = round(sample["elapsed_seconds"], 4)
            row["原始标注一致率（可选诊断）"] = format_accuracy(
                sample["dataset_annotation_diagnostic"][
                    "dataset_annotation_consistency_rate"
                ]
            )
            row["错误"] = None
        else:
            row["识别字段数"] = None
            row["warnings数"] = None
            row["耗时（秒）"] = None
            row["原始标注一致率（可选诊断）"] = None
            row["错误"] = f"{sample['error_type']}: {sample['message']}"
        sample_rows.append(row)
    st.subheader("逐样本状态")
    st.dataframe(sample_rows, hide_index=True, width="stretch")

    st.subheader("各难度工程汇总")
    difficulty_rows = []
    for difficulty in ("simple", "medium", "complex"):
        group = payload["difficulty_summary"][difficulty]
        difficulty_rows.append(
            {
                "难度": DIFFICULTY_LABELS[difficulty],
                "成功": group["successful_sample_count"],
                "失败": group["failed_sample_count"],
                "识别字段总数": group["total_field_count"],
                "warnings总数": group["total_warning_count"],
                "总耗时（秒）": group["total_elapsed_seconds"],
                "平均耗时（秒）": group["mean_elapsed_seconds"],
                "原始标注一致率（可选诊断）": format_accuracy(
                    group["dataset_annotation_diagnostic"][
                        "dataset_annotation_consistency_rate"
                    ]
                ),
            }
        )
    st.dataframe(difficulty_rows, hide_index=True, width="stretch")
    st.subheader("固定验证工程汇总")
    engineering = payload["engineering_summary"]
    engineering_columns = st.columns(4)
    engineering_columns[0].metric(
        "识别字段总数", engineering["total_field_count"]
    )
    engineering_columns[1].metric(
        "warnings总数", engineering["total_warning_count"]
    )
    engineering_columns[2].metric(
        "总耗时（秒）", engineering["total_elapsed_seconds"]
    )
    engineering_columns[3].metric(
        "平均耗时（秒）", engineering["mean_elapsed_seconds"]
    )
    st.info(
        "固定验证用于检查视觉模型调用和工程流程，不计算“参考字段识别正确率”。"
    )
    with st.expander("可选诊断：XFUND原始标注一致性（不代表正确率）"):
        render_dataset_summary(
            payload["overall_dataset_annotation_diagnostic"]
        )
    st.caption(f"本地验证文件：{outcome['output_file']}")
    st.download_button(
        "下载本次固定验证JSON",
        data=json_bytes(payload),
        file_name=f"validation_{payload['metadata']['validation_run_id']}.json",
        mime="application/json",
        key=f"download_validation_{payload['metadata']['validation_run_id']}",
    )
    st.info(
        "适合截图：逐样本状态、工程汇总和验证完整性。"
        "截图前请隐藏本地路径及不必要的字段值。"
    )


def render_validation_tab(context: dict[str, Any]) -> None:
    st.header("验证结果")
    st.caption("每次点击都会按冻结顺序现场串行调用6张样本；历史结果不会替代本次调用。")
    if not context["h3_ready"]:
        st.warning(
            "H3尚未冻结；当前页面只读，固定验证调用已禁用。"
        )
    else:
        st.info(
            "固定验证只检查6张样本的视觉模型调用与工程流程。"
            "不要求逐字段修复XFUND原始标注，也不计算参考字段识别正确率；"
            "原始标注一致性仅作为可选诊断。"
        )
    validation_samples = context["subset"]["validation"]["samples"]
    st.dataframe(
        [
            {
                "顺序": item["validation_order"],
                "样本": item["sample_id"],
                "难度": DIFFICULTY_LABELS[item["difficulty_group"]],
            }
            for item in validation_samples
        ],
        hide_index=True,
        width="stretch",
    )
    confirmed = st.checkbox(
        "我确认本次点击会现场串行产生6次真实模型调用",
        key="validation_confirm",
        disabled=not context["h3_ready"],
    )
    clicked = st.button(
        "运行固定验证",
        type="primary",
        disabled=(
            not context["h3_ready"]
            or st.session_state.get("validation_running", False)
        ),
    )
    if clicked and not confirmed:
        st.warning("请先勾选固定验证调用确认。")
    if should_start_real_run(
        button_clicked=clicked,
        confirmation_checked=confirmed,
        currently_running=st.session_state.get("validation_running", False),
    ):
        st.session_state["validation_running"] = True
        settings = None
        progress_bar = st.progress(0)
        status_box = st.empty()

        def progress(index: int, total: int, sample_id: str, status: str) -> None:
            labels = {"running": "正在运行", "success": "成功", "failed": "失败"}
            if status != "running":
                progress_bar.progress(index / total)
            status_box.write(f"[{index}/{total}] {sample_id}：{labels[status]}")

        try:
            require_h3_frozen(context["candidate"])
            settings = load_model_settings()
            client = OpenAICompatibleVisionClient(settings)
            outcome = run_fixed_validation(
                validation_samples=validation_samples,
                documents=context["documents"],
                images_dir=context["images_dir"],
                client=client,
                results_dir=RESULTS_DIR,
                project_root=PROJECT_ROOT,
                secrets=(settings.api_key,),
                progress_callback=progress,
            )
            st.session_state["validation_result"] = {"outcome": outcome}
        except Exception as error:
            secrets = (settings.api_key,) if settings is not None else ()
            st.session_state["validation_result"] = {
                "error": f"{type(error).__name__}: {safe_error_message(error, secrets)}"
            }
        finally:
            st.session_state["validation_running"] = False

    if st.session_state.get("validation_result"):
        render_validation_result(st.session_state["validation_result"])


def main() -> None:
    st.set_page_config(
        page_title="中文表单结构化识别助手",
        page_icon="📄",
        layout="wide",
    )
    st.title("基于视觉大模型的中文表单结构化识别助手")
    st.caption("XFUND中文真实数据｜固定模型｜程序确定性比较｜用户主动触发调用")
    try:
        context = load_app_context()
    except Exception as error:
        st.error(f"应用初始化失败：{type(error).__name__}: {error}")
        st.stop()
    if context["h3_ready"]:
        st.info(
            f"H3冻结模型：{context['candidate']['model_id']}｜Prompt v1｜Schema v1。"
            "页面查看、切换标签页、展开结果和下载JSON不会自动调用模型。"
        )
    else:
        st.warning(
            f"固定模型仍为{context['candidate']['model_id']}，"
            "比较规则v2已通过，最终参考结果仍在人工复核。"
            "页面可以查看，所有真实模型调用按钮已禁用。"
        )
    single_tab, validation_tab = st.tabs(["单张表单识别", "验证结果"])
    with single_tab:
        render_single_tab(context)
    with validation_tab:
        render_validation_tab(context)


if __name__ == "__main__":
    main()
