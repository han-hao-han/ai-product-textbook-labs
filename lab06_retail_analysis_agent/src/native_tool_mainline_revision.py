"""Offline contract checks for the reopened V2.1 native-tool mainline."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REVISION_PATH = (
    PROJECT_ROOT
    / "config"
    / "h3_native_tool_agent_v2_1_revision.candidate.json"
)
HISTORICAL_V2_1_PATH = (
    PROJECT_ROOT
    / "config"
    / "h3_tool_plan_semantic_support_v2_1_contract.json"
)
OLD_REAL_PLAN_PATH = (
    PROJECT_ROOT
    / "config"
    / "h3_v2_1_real_validation_plan.candidate.json"
)
TOOL_CONTRACT_PATH = (
    PROJECT_ROOT / "config" / "h3_tool_contract.json"
)


class NativeToolMainlineRevisionError(ValueError):
    """Raised when the candidate drifts from the 1.5.6 mainline."""


@dataclass(frozen=True)
class NativeToolMainlineRevisionCheck:
    status: str
    tool_count: int
    model_selects_tool: bool
    model_generates_arguments: bool
    model_decides_continue: bool
    model_organizes_report: bool
    program_builds_charts: bool
    program_preselects_next_tool: bool
    real_model_calls_allowed: bool
    provisional_representative_response_count: int
    checks: tuple[str, ...]


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise NativeToolMainlineRevisionError(
            f"{path.name}顶层必须是JSON对象"
        )
    return value


def load_native_tool_mainline_revision() -> dict[str, Any]:
    return _read_json(REVISION_PATH)


def validate_native_tool_mainline_revision(
    candidate: dict[str, Any] | None = None,
) -> NativeToolMainlineRevisionCheck:
    revision = (
        deepcopy(candidate)
        if candidate is not None
        else load_native_tool_mainline_revision()
    )
    historical = _read_json(HISTORICAL_V2_1_PATH)
    old_real_plan = _read_json(OLD_REAL_PLAN_PATH)
    tool_contract = _read_json(TOOL_CONTRACT_PATH)
    checks: list[str] = []

    if revision.get("status") not in {
        "candidate_pending_offline_protocol_validation_and_user_freeze",
        (
            "independent_native_tool_mock_validated_pending_"
            "offline_transport_and_user_freeze"
        ),
        (
            "offline_transport_validated_pending_user_freeze_"
            "and_real_plan_redesign"
        ),
        (
            "real_plan_redesigned_offline_preflight_passed_"
            "pending_user_freeze"
        ),
        (
            "five_response_real_plan_frozen_pending_"
            "compatible_call_authorization"
        ),
        (
            "five_response_real_plan_frozen_and_call_authorized_"
            "pending_execution"
        ),
        "five_response_real_runner_offline_validated_pending_execution",
        (
            "real_validation_failed_first_response_invalid_arguments_"
            "pending_user_decision"
        ),
    }:
        raise NativeToolMainlineRevisionError(
            "主线修正版必须保持候选且等待离线协议验证"
        )
    if revision.get("reopens", {}).get(
        "real_model_calls_allowed"
    ):
        raise NativeToolMainlineRevisionError(
            "重新打开设计边界不等于授权真实模型调用"
        )
    checks.append("candidate_has_no_real_call_authority")

    if historical.get("status") != (
        "reopened_by_user_for_mainline_correction"
    ):
        raise NativeToolMainlineRevisionError(
            "历史V2.1必须记录为因主线冲突重新打开"
        )
    expected_scope = {
        "模型原生选择白名单工具",
        "模型生成参数并决定是否继续调用",
        "模型基于FACT组织报告",
        "FACT、图表和报告统一接入",
    }
    if set(
        historical.get("reopening", {}).get("scope", [])
    ) != expected_scope:
        raise NativeToolMainlineRevisionError(
            "重新打开范围必须精确覆盖四项主线边界"
        )
    checks.append("historical_v2_1_reopened_in_exact_scope")

    tools = tool_contract.get("tools")
    if not isinstance(tools, list) or len(tools) != 7:
        raise NativeToolMainlineRevisionError(
            "主线修正版必须继续使用七个冻结白名单工具"
        )
    checks.append("seven_frozen_tools_retained")

    protocol = revision.get("native_tool_protocol", {})
    required_true = (
        "model_must_choose_tool_name",
        "model_must_generate_tool_arguments",
        "model_must_decide_continue_or_finish",
    )
    for field_name in required_true:
        if protocol.get(field_name) is not True:
            raise NativeToolMainlineRevisionError(
                f"{field_name}必须为true"
            )
    if protocol.get("program_may_preselect_next_tool") is not False:
        raise NativeToolMainlineRevisionError(
            "程序不得在模型响应前预选下一工具"
        )
    if (
        protocol.get("program_may_generate_model_tool_arguments")
        is not False
    ):
        raise NativeToolMainlineRevisionError(
            "程序不得替模型生成工具参数再要求原样返回"
        )
    visibility = str(protocol.get("initial_tool_visibility", ""))
    if "全部七个" not in visibility:
        raise NativeToolMainlineRevisionError(
            "模型选择工具时必须同时看到全部七个白名单工具"
        )
    if protocol.get("per_response_tool_call_limit") != 1:
        raise NativeToolMainlineRevisionError(
            "单响应最多只能包含一个原生工具调用"
        )
    if protocol.get("per_turn_tool_call_limit") != 4:
        raise NativeToolMainlineRevisionError(
            "单轮工具调用上限必须保持为4"
        )
    checks.append("model_native_tool_choice_and_short_loop")

    recipe_role = revision.get(
        "tool_validation_boundary",
        {},
    ).get("analysis_recipe_role", {})
    if (
        recipe_role.get("active_router") is not False
        or recipe_role.get("model_decision_type") is not False
    ):
        raise NativeToolMainlineRevisionError(
            "分析配方只能用于调用后的验证，不能继续做主动路由"
        )
    forbidden_recipe_uses = set(
        recipe_role.get("forbidden_use", [])
    )
    if {
        "在模型调用前决定工具名",
        "只向模型暴露配方的下一工具",
        "替模型生成全部参数",
    } - forbidden_recipe_uses:
        raise NativeToolMainlineRevisionError(
            "候选契约必须明确禁止三种recipe路由方式"
        )
    checks.append("recipes_are_posthoc_validators_not_router")

    dependency = revision.get("dependent_call_boundary", {})
    if (
        dependency.get("program_may_silently_replace_wrong_arguments")
        is not False
        or dependency.get(
            "program_may_hardcode_peak_month_before_first_call"
        )
        is not False
    ):
        raise NativeToolMainlineRevisionError(
            "Q06依赖参数错误时必须失败，程序不得静默替换"
        )
    checks.append("dependent_arguments_are_model_generated_fact_checked")

    report = revision.get("report_boundary", {})
    if report.get("model_organizes_report") is not True:
        raise NativeToolMainlineRevisionError(
            "模型必须负责基于FACT组织报告"
        )
    if report.get("program_renders_all_business_text") is not False:
        raise NativeToolMainlineRevisionError(
            "程序不得重新接管全部正式报告文字"
        )
    terminal = report.get("q06_terminal_permission", {})
    if (
        terminal.get("tool_visibility") != 7
        or terminal.get("tool_choice") != "none"
        or terminal.get("program_preselects_business_tool") is not False
        or terminal.get("model_organizes_report") is not True
    ):
        raise NativeToolMainlineRevisionError(
            "Q06证据完整后必须只收回工具调用权限"
        )
    report_checks = set(report.get("program_checks", []))
    if not any("所有数字" in item for item in report_checks):
        raise NativeToolMainlineRevisionError(
            "程序必须校验模型报告的全部数字来自引用FACT"
        )
    checks.append("model_report_program_fact_validation")

    charts = revision.get("chart_boundary", {})
    if (
        charts.get("model_selects_chart") is not True
        or charts.get("model_generates_chart_code") is not False
        or charts.get("model_modifies_chart_values") is not False
        or charts.get("program_builds_chart_data") is not True
    ):
        raise NativeToolMainlineRevisionError(
            "图表必须由模型选白名单类型、程序使用同源FACT构建"
        )
    if len(charts.get("whitelist", [])) != 4:
        raise NativeToolMainlineRevisionError(
            "图表白名单必须保持四种"
        )
    checks.append("chart_and_report_share_current_tool_facts")

    split = revision.get("responsibility_split", {})
    if set(split) != {"model", "tools", "program", "human"}:
        raise NativeToolMainlineRevisionError(
            "职责必须明确分为模型、工具、程序和人工"
        )
    checks.append("four_party_responsibility_split")

    if old_real_plan.get("status") != (
        "paused_after_mainline_boundaries_reopened"
    ):
        raise NativeToolMainlineRevisionError(
            "旧六次真实验证方案必须暂停"
        )
    if old_real_plan.get("pause", {}).get(
        "real_model_calls_allowed"
    ):
        raise NativeToolMainlineRevisionError(
            "暂停方案不得保留真实调用权限"
        )
    checks.append("old_real_validation_plan_paused")

    real_validation = revision.get("real_validation", {})
    if real_validation.get("real_model_calls_allowed"):
        raise NativeToolMainlineRevisionError(
            "主线修正版离线验证前不得允许真实模型调用"
        )
    if real_validation.get("previous_online_entry_retired") is not True:
        raise NativeToolMainlineRevisionError(
            "旧recipe在线入口必须保持停用"
        )
    if (
        real_validation.get(
            "provisional_expected_response_count_if_all_pass"
        )
        != 5
    ):
        raise NativeToolMainlineRevisionError(
            "Q06、Q08、Q09的暂定响应数必须按原生循环重算为5"
        )
    checks.append("real_validation_count_is_provisional_not_authorized")

    return NativeToolMainlineRevisionCheck(
        status="passed",
        tool_count=7,
        model_selects_tool=True,
        model_generates_arguments=True,
        model_decides_continue=True,
        model_organizes_report=True,
        program_builds_charts=True,
        program_preselects_next_tool=False,
        real_model_calls_allowed=False,
        provisional_representative_response_count=5,
        checks=tuple(checks),
    )
