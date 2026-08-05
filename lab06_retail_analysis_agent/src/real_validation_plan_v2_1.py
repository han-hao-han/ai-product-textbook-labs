"""Deterministic preflight checks for the V2.1 real-model validation plan."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = (
    PROJECT_ROOT
    / "config"
    / "h3_v2_1_real_validation_plan.candidate.json"
)
QUESTION_PATH = (
    PROJECT_ROOT / "config" / "h2_validation_questions.json"
)
V2_1_CONTRACT_PATH = (
    PROJECT_ROOT
    / "config"
    / "h3_tool_plan_semantic_support_v2_1_contract.json"
)
TECHNICAL_CANDIDATE_PATH = (
    PROJECT_ROOT / "config" / "h3_technical_contract.candidate.json"
)


class RealValidationPlanV2_1Error(ValueError):
    """Raised when a real-model plan violates the frozen preflight."""


@dataclass(frozen=True)
class RealValidationPlanPreflightV2_1:
    status: str
    question_ids: tuple[str, ...]
    request_attempt_upper_bound: int
    expected_standard_json_requests: int
    expected_beta_strict_tool_requests: int
    automatic_retry_count: int
    stop_on_first_case_failure: bool
    real_model_calls_allowed: bool
    checks: tuple[str, ...]


EXPECTED_CASES = {
    "Q06": {
        "order": 1,
        "attempts": 4,
        "terminal": "completed",
        "tool_sequence": [
            "analyze_time_trend",
            "rank_products",
        ],
        "recipe_id": "peak_month_product_ranking",
    },
    "Q08": {
        "order": 2,
        "attempts": 1,
        "terminal": "needs_clarification",
        "tool_sequence": [],
        "decision_type": "clarification",
    },
    "Q09": {
        "order": 3,
        "attempts": 1,
        "terminal": "boundary",
        "tool_sequence": [],
        "decision_type": "boundary",
    },
}
EXPECTED_QUESTION_IDS = tuple(EXPECTED_CASES)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RealValidationPlanV2_1Error(
            f"{path.name}顶层必须是JSON对象"
        )
    return value


def load_real_validation_plan_v2_1() -> dict[str, Any]:
    return _read_json(PLAN_PATH)


def validate_real_validation_plan_v2_1(
    plan: dict[str, Any] | None = None,
) -> RealValidationPlanPreflightV2_1:
    candidate = (
        deepcopy(plan)
        if plan is not None
        else load_real_validation_plan_v2_1()
    )
    questions = _read_json(QUESTION_PATH)
    frozen_contract = _read_json(V2_1_CONTRACT_PATH)
    technical = _read_json(TECHNICAL_CANDIDATE_PATH)
    checks: list[str] = []

    if candidate.get("status") != (
        "candidate_pending_user_freeze_and_separate_call_authorization"
    ):
        raise RealValidationPlanV2_1Error(
            "方案状态必须保持候选且等待独立真实调用授权"
        )
    if candidate.get("model") != "deepseek-v4-pro":
        raise RealValidationPlanV2_1Error(
            "方案模型必须是用户选定的deepseek-v4-pro"
        )
    authorization = candidate.get("authorization", {})
    if authorization.get("real_model_calls_allowed_by_this_plan"):
        raise RealValidationPlanV2_1Error(
            "方案设计本身不得授权真实模型调用"
        )
    if authorization.get("api_key_may_be_read_during_plan_design"):
        raise RealValidationPlanV2_1Error(
            "方案设计阶段不得读取API Key"
        )
    if authorization.get("network_may_be_opened_during_plan_design"):
        raise RealValidationPlanV2_1Error(
            "方案设计阶段不得打开网络"
        )
    checks.append("design_has_no_real_call_authority")

    if questions.get("status") != "frozen_by_user":
        raise RealValidationPlanV2_1Error("H2固定问题必须保持冻结")
    question_ids = {
        item["id"] for item in questions.get("questions", [])
    }
    if not set(EXPECTED_QUESTION_IDS).issubset(question_ids):
        raise RealValidationPlanV2_1Error(
            "代表问题必须全部来自冻结Q01至Q10"
        )
    checks.append("selected_questions_are_frozen_h2_questions")

    if frozen_contract.get("status") != "frozen_by_user":
        raise RealValidationPlanV2_1Error("V2.1边界必须保持冻结")
    if frozen_contract.get("authorization", {}).get(
        "real_model_calls_allowed"
    ):
        raise RealValidationPlanV2_1Error(
            "冻结V2.1边界不得被静默改成允许真实调用"
        )
    checks.append("v2_1_boundary_remains_frozen")

    online_transport = technical[
        "tool_plan_semantic_support_v2_1_candidate"
    ]["online_candidate_transport"]
    if online_transport.get("real_model_called"):
        raise RealValidationPlanV2_1Error(
            "在线候选证据当前必须仍是离线传输验证"
        )
    checks.append("online_candidate_is_offline_validated_only")

    technical_plan = technical.get(
        "v2_1_real_validation_plan_candidate",
        {},
    )
    if technical_plan.get("status") != (
        "designed_and_offline_preflight_passed_pending_user_freeze"
    ):
        raise RealValidationPlanV2_1Error(
            "技术候选必须记录方案已设计但仍等待用户冻结"
        )
    if (
        technical_plan.get("real_model_calls_allowed") is not False
        or technical_plan.get("real_model_called") is not False
        or technical_plan.get("request_attempt_upper_bound") != 6
    ):
        raise RealValidationPlanV2_1Error(
            "技术候选不得把方案设计记录成真实调用或改变六次上限"
        )
    if technical_plan.get("runner_enforcement_status") != (
        "pending_plan_freeze_before_implementation"
    ):
        raise RealValidationPlanV2_1Error(
            "方案冻结前不得声称逐题门控已接入在线入口"
        )
    checks.append("technical_candidate_records_design_not_execution")

    selected = tuple(
        candidate.get("selection_strategy", {}).get(
            "selected_question_ids_in_order",
            [],
        )
    )
    if selected != EXPECTED_QUESTION_IDS:
        raise RealValidationPlanV2_1Error(
            "首轮代表问题及顺序必须固定为Q06、Q08、Q09"
        )
    baseline_ids = tuple(
        candidate.get("comparison_baseline", {}).get(
            "question_ids",
            [],
        )
    )
    if baseline_ids != EXPECTED_QUESTION_IDS:
        raise RealValidationPlanV2_1Error(
            "V2对照问题必须与V2.1代表问题完全相同"
        )
    checks.append("same_questions_as_v2_baseline")

    raw_cases = candidate.get("case_gates")
    if not isinstance(raw_cases, list) or len(raw_cases) != 3:
        raise RealValidationPlanV2_1Error(
            "方案必须且只能包含三个逐题门"
        )
    case_by_id = {
        item.get("question_id"): item for item in raw_cases
    }
    if tuple(
        item.get("question_id") for item in raw_cases
    ) != EXPECTED_QUESTION_IDS:
        raise RealValidationPlanV2_1Error(
            "逐题门顺序必须是Q06、Q08、Q09"
        )
    expected_attempts = 0
    for question_id, expected in EXPECTED_CASES.items():
        case = case_by_id.get(question_id)
        if not isinstance(case, dict):
            raise RealValidationPlanV2_1Error(
                f"缺少{question_id}逐题门"
            )
        if case.get("order") != expected["order"]:
            raise RealValidationPlanV2_1Error(
                f"{question_id}顺序不符合冻结方案"
            )
        if (
            case.get("expected_request_attempts")
            != expected["attempts"]
        ):
            raise RealValidationPlanV2_1Error(
                f"{question_id}请求数不符合协议阶段数"
            )
        if (
            case.get("expected_terminal_status")
            != expected["terminal"]
        ):
            raise RealValidationPlanV2_1Error(
                f"{question_id}终态不符合固定问题"
            )
        if (
            case.get("expected_tool_sequence")
            != expected["tool_sequence"]
        ):
            raise RealValidationPlanV2_1Error(
                f"{question_id}工具序列不符合V2.1边界"
            )
        decision = case.get("expected_decision", {})
        if "recipe_id" in expected and (
            decision.get("recipe_id") != expected["recipe_id"]
        ):
            raise RealValidationPlanV2_1Error(
                f"{question_id}分析配方不正确"
            )
        if "decision_type" in expected and (
            decision.get("decision_type")
            != expected["decision_type"]
        ):
            raise RealValidationPlanV2_1Error(
                f"{question_id}决策类型不正确"
            )
        expected_attempts += expected["attempts"]
    checks.append("case_gates_match_v2_1_protocol")

    limits = candidate.get("hard_limits", {})
    upper_bound = limits.get("request_attempt_upper_bound")
    if upper_bound != expected_attempts or upper_bound != 6:
        raise RealValidationPlanV2_1Error(
            "请求尝试硬上限必须等于三题协议阶段总数6"
        )
    if limits.get("automatic_retry_count") != 0:
        raise RealValidationPlanV2_1Error("真实验证不得自动重试")
    if limits.get("parallel_requests") is not False:
        raise RealValidationPlanV2_1Error("真实验证必须串行执行")
    if limits.get("stop_on_first_case_failure") is not True:
        raise RealValidationPlanV2_1Error(
            "真实验证必须在首个逐题门失败后停止"
        )
    if limits.get("reserve_attempt_before_transport") is not True:
        raise RealValidationPlanV2_1Error(
            "请求必须在传输前占用硬上限"
        )
    endpoints = limits.get("expected_endpoint_counts_if_all_pass", {})
    if endpoints != {
        "standard_json": 4,
        "beta_strict_tool": 2,
        "total": 6,
    }:
        raise RealValidationPlanV2_1Error(
            "预期端点计数必须为4个JSON加2个strict工具请求"
        )
    checks.append("six_attempt_zero_retry_serial_gate")

    acceptance = candidate.get("stage_acceptance", {})
    if (
        acceptance.get("all_case_gates_must_pass") is not True
        or acceptance.get("partial_pass_does_not_pass_stage")
        is not True
        or acceptance.get("manual_review_required") is not True
        or acceptance.get("h3_may_be_frozen_automatically")
        is not False
    ):
        raise RealValidationPlanV2_1Error(
            "整阶段必须全通过、人工检查且不得自动冻结H3"
        )
    checks.append("stage_requires_all_cases_and_manual_review")

    change = candidate.get("change_control", {})
    for field_name in (
        "question_ids_frozen_before_call",
        "request_attempt_upper_bound_frozen_before_call",
        "acceptance_rules_frozen_before_call",
        "real_call_authorized",
    ):
        if change.get(field_name) is not False:
            raise RealValidationPlanV2_1Error(
                f"候选设计阶段{field_name}必须为false"
            )
    checks.append("freeze_and_authorization_are_still_pending")

    return RealValidationPlanPreflightV2_1(
        status="passed",
        question_ids=selected,
        request_attempt_upper_bound=upper_bound,
        expected_standard_json_requests=4,
        expected_beta_strict_tool_requests=2,
        automatic_retry_count=0,
        stop_on_first_case_failure=True,
        real_model_calls_allowed=False,
        checks=tuple(checks),
    )
