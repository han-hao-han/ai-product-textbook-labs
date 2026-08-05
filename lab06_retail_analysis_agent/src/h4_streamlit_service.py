"""Testable H4 application services shared by Streamlit and automated checks."""

from __future__ import annotations

import csv
import io
import json
import zipfile
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from src.agent_orchestrator import AgentTurnOutcome, ExecutedToolCall
from src.chart_data import ChartData, build_chart_data
from src.chat_runtime_v1 import (
    CHAT_REAL_MODEL_CONFIRMATION,
    MAX_CHAT_MODEL_RESPONSES,
    NativeToolChatRuntimeV1,
)
from src.conversation_state import (
    ConditionOperation,
    ConditionResolution,
    EffectiveConditions,
    resolve_conditions,
)
from src.data_audit import read_online_retail_workbook, sha256_file
from src.fact_builder import FactBuildContext, FactBuilder
from src.fact_schema import FactRecord
from src.fixed_question_validation import (
    FixedQuestionValidationResult,
    load_frozen_questions,
    validate_fixed_question,
)
from src.offline_mode import ModePolicy, build_mode_policy
from src.online_native_tool_candidate_claim_controller_v3_1 import (
    NativeToolOnlineCandidateClaimControllerV3_1,
)
from src.online_native_tool_candidate_v2_1_revision import (
    NATIVE_REAL_MODEL_CONFIRMATION,
)
from src.retail_cleaning import RetailDataLayers, build_retail_data_layers
from src.retail_tools import RetailToolService
from src.run_record import (
    FailureRecord,
    SessionRunRecord,
    ToolCallRecord,
    TurnRunRecord,
    validate_record_security,
)
from src.tool_registry import RetailToolRegistry


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKBOOK_PATH = PROJECT_ROOT / "data" / "raw" / "Online Retail.xlsx"
CACHE_ROOT = PROJECT_ROOT / "data" / "cache" / "streamlit_retail_layers_v1"
METRIC_CONTRACT_PATH = PROJECT_ROOT / "config" / "h2_metric_contract.json"
EXPECTED_WORKBOOK_SHA256 = (
    "43465a06f2ccf7c8b5bd2892bc7defb52f97487934fe93b16ae4c3936424676d"
)
MODEL_ID = "deepseek-v4-flash"
MODEL_PROVIDER = "DeepSeek"
MAX_RESPONSES_PER_TURN = 5
CACHE_SCHEMA_VERSION = "1.5.6-h4-streamlit-data-cache-v1"

TOOL_LABELS = {
    "get_data_profile": "数据概况",
    "get_sales_overview": "销售概览",
    "rank_products": "商品排名",
    "analyze_regions": "地区分析",
    "analyze_time_trend": "时间趋势",
    "analyze_customers": "客户聚合分析",
    "compare_segments": "英国与非英国分段比较",
}
ANALYSIS_OBJECTS = {
    "get_data_profile": None,
    "get_sales_overview": "sales",
    "rank_products": "product",
    "analyze_regions": "region",
    "analyze_time_trend": "time",
    "analyze_customers": "customer",
    "compare_segments": "segments",
}
CHART_DEFAULTS = {
    "rank_products": ("top_n_horizontal_bar", "商品经营排名"),
    "analyze_regions": ("vertical_bar", "地区经营概览"),
    "analyze_time_trend": ("monthly_line", "月度经营趋势"),
    "compare_segments": ("two_segment_share_bar", "客户分群对比"),
}


class H4ServiceError(RuntimeError):
    """Raised when an H4 reader-facing operation cannot safely complete."""


@dataclass(frozen=True)
class OfflineToolExperience:
    session_id: str
    turn_id: str
    tool_name: str
    arguments: dict[str, Any]
    result: dict[str, Any]
    facts: tuple[FactRecord, ...]
    chart: ChartData | None


@dataclass(frozen=True)
class OnlineTurnExperience:
    question_id: str | None
    displayed_question: str
    submitted_question: str
    outcome: AgentTurnOutcome
    validation: FixedQuestionValidationResult | None
    condition_resolution: ConditionResolution
    response_limit: int
    response_attempted: int
    transport_audit: dict[str, Any]
    trace: tuple[Any, ...]
    saved_paths: tuple[str, ...]
    clarification_answer: str | None = None
    clarification_message: str | None = None
    runtime_kind: str = "fixed_question_harness"


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise H4ServiceError(f"{path.name}必须是JSON对象")
    return value


def load_reader_contracts() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    return load_json(METRIC_CONTRACT_PATH), load_frozen_questions()


def mode_policy(api_key: str | None) -> ModePolicy:
    return build_mode_policy(api_key_configured=bool(api_key and api_key.strip()))


def _load_cached_layers(cache_root: Path, workbook_sha256: str) -> RetailDataLayers | None:
    manifest_path = cache_root / "manifest.json"
    classified_path = cache_root / "classified.parquet"
    sales_path = cache_root / "sales_fact.parquet"
    if not all(path.is_file() for path in (manifest_path, classified_path, sales_path)):
        return None
    try:
        manifest = load_json(manifest_path)
        if (
            manifest.get("schema_version") != CACHE_SCHEMA_VERSION
            or manifest.get("workbook_sha256") != workbook_sha256
            or manifest.get("metric_contract_version")
            != "1.5.6-h2-metric-contract-v1"
        ):
            return None
        classified = pd.read_parquet(classified_path)
        sales_fact = pd.read_parquet(sales_path)
    except Exception:
        return None
    customer_fact = sales_fact.loc[sales_fact["customer_id"].notna()].copy()
    active = ~classified["is_exact_duplicate_after_first"]
    exceptions = classified.loc[
        active & ~classified["record_class"].eq("sale")
    ].copy()
    if (
        len(classified) != manifest.get("classified_rows")
        or len(sales_fact) != manifest.get("sales_fact_rows")
        or len(customer_fact) != manifest.get("customer_fact_rows")
        or len(exceptions) != manifest.get("exception_rows")
    ):
        return None
    return RetailDataLayers(classified, sales_fact, customer_fact, exceptions)


def prepare_runtime_cache(
    workbook_path: Path = WORKBOOK_PATH,
    cache_root: Path = CACHE_ROOT,
) -> dict[str, Any]:
    """Create a local-only Parquet cache from the immutable official workbook."""

    if not workbook_path.is_file():
        raise H4ServiceError(
            "固定数据文件不存在，请先运行 scripts/download_online_retail.py。"
        )
    digest = sha256_file(workbook_path)
    if digest != EXPECTED_WORKBOOK_SHA256:
        raise H4ServiceError("固定数据文件SHA-256与H2冻结值不一致，已停止执行。")
    cached = _load_cached_layers(cache_root, digest)
    if cached is not None:
        return {
            "status": "reused",
            "schema_version": CACHE_SCHEMA_VERSION,
            "workbook_sha256": digest,
            "classified_rows": len(cached.classified),
            "sales_fact_rows": len(cached.sales_fact),
            "customer_fact_rows": len(cached.customer_fact),
            "exception_rows": len(cached.exceptions),
        }
    frame, _ = read_online_retail_workbook(workbook_path)
    layers = build_retail_data_layers(frame)
    cache_root.mkdir(parents=True, exist_ok=True)
    classified_temporary = cache_root / "classified.parquet.tmp"
    sales_temporary = cache_root / "sales_fact.parquet.tmp"
    layers.classified.to_parquet(classified_temporary, index=False)
    layers.sales_fact.to_parquet(sales_temporary, index=False)
    classified_temporary.replace(cache_root / "classified.parquet")
    sales_temporary.replace(cache_root / "sales_fact.parquet")
    manifest = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "workbook_sha256": digest,
        "metric_contract_version": "1.5.6-h2-metric-contract-v1",
        "classified_rows": len(layers.classified),
        "sales_fact_rows": len(layers.sales_fact),
        "customer_fact_rows": len(layers.customer_fact),
        "exception_rows": len(layers.exceptions),
        "contains_raw_customer_ids": True,
        "repository_distribution_allowed": False,
    }
    _write_json(cache_root / "manifest.json", manifest)
    return {"status": "created", **manifest}


def build_real_registry(workbook_path: Path = WORKBOOK_PATH) -> RetailToolRegistry:
    digest = sha256_file(workbook_path) if workbook_path.is_file() else ""
    layers = _load_cached_layers(CACHE_ROOT, digest) if digest else None
    if layers is None:
        prepare_runtime_cache(workbook_path, CACHE_ROOT)
        layers = _load_cached_layers(CACHE_ROOT, EXPECTED_WORKBOOK_SHA256)
    if layers is None:
        raise H4ServiceError("本地运行缓存创建后仍无法通过一致性校验。")
    return RetailToolRegistry(RetailToolService(layers))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _relative_turn_root(session_id: str, turn_id: str) -> str:
    return f"results/raw/streamlit_sessions/{session_id}/{turn_id}"


def _save_tool_result(call: ExecutedToolCall) -> str:
    relative = call.result_path.replace("\\", "/")
    _write_json(PROJECT_ROOT / relative, call.result)
    return relative


def _outcome_payload(outcome: AgentTurnOutcome) -> dict[str, Any]:
    return {
        "status": outcome.status,
        "session_id": outcome.session_id,
        "turn_id": outcome.turn_id,
        "original_question": outcome.original_question,
        "model_response_count": outcome.model_response_count,
        "tool_calls": [
            {
                "call_id": call.call_id,
                "provider_call_id": call.provider_call_id,
                "tool_name": call.tool_name,
                "arguments": call.arguments,
                "result_path": call.result_path,
                "result": call.result,
                "fact_ids": [fact.fact_id for fact in call.facts],
            }
            for call in outcome.tool_calls
        ],
        "facts": [fact.model_dump(mode="json") for fact in outcome.facts],
        "charts": [chart.model_dump(mode="json") for chart in outcome.charts],
        "report_markdown": outcome.report_markdown,
        "report_validation": (
            outcome.report_validation.model_dump(mode="json")
            if outcome.report_validation is not None
            else None
        ),
        "clarification": (
            outcome.clarification.model_dump(mode="json")
            if outcome.clarification is not None
            else None
        ),
        "boundary": (
            outcome.boundary.model_dump(mode="json")
            if outcome.boundary is not None
            else None
        ),
        "error_stage": outcome.error_stage,
        "error_message": outcome.error_message,
    }


class ResponseEventJournal:
    """Append each transport event so a page/process crash keeps prior evidence."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _json_safe(value: Any) -> Any:
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        if isinstance(value, dict):
            return {
                str(key): ResponseEventJournal._json_safe(item)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [ResponseEventJournal._json_safe(item) for item in value]
        return value

    def __call__(self, event_type: str, payload: dict[str, Any]) -> None:
        entry = {
            "recorded_at": datetime.now().astimezone().isoformat(),
            "event_type": event_type,
            "payload": self._json_safe(payload),
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


class SessionContextStrictClient:
    """Add current-session conditions without changing the first user question.

    Keeping the original fixed question as the first user message preserves the
    frozen terminal lock and Harness semantics.  The context is appended to the
    existing system instruction and never contains historical FACT values.
    """

    def __init__(self, delegate: Any, context: str) -> None:
        self.delegate = delegate
        self.context = context

    def __getattr__(self, name: str) -> Any:
        return getattr(self.delegate, name)

    def complete_strict_tools(self, **kwargs: Any):
        messages = [dict(item) for item in kwargs["messages"]]
        if messages and messages[0].get("role") == "system":
            messages[0]["content"] = (
                str(messages[0].get("content", "")) + "\n\n" + self.context
            )
        kwargs["messages"] = messages
        return self.delegate.complete_strict_tools(**kwargs)


def run_manual_tool(
    *,
    registry: RetailToolRegistry,
    session_id: str,
    turn_id: str,
    tool_name: str,
    arguments: dict[str, Any],
) -> OfflineToolExperience:
    """Run one user-selected tool; this is explicitly not Agent behavior."""

    result = registry.execute(tool_name, arguments)
    relative_root = _relative_turn_root(session_id, turn_id)
    result_path = f"{relative_root}/CALL-001/result.json"
    facts = tuple(
        FactBuilder().build(
            result,
            FactBuildContext(
                session_id=session_id,
                turn_id=turn_id,
                call_id="CALL-001",
                source_result_path=result_path,
            ),
        )
    )
    _write_json(PROJECT_ROOT / result_path, result)
    chart: ChartData | None = None
    if tool_name in CHART_DEFAULTS:
        chart_type, title = CHART_DEFAULTS[tool_name]
        chart = build_chart_data(
            chart_id="CHART-001",
            chart_type=chart_type,
            title=title,
            tool_result=result,
            facts=list(facts),
        )
    _write_json(
        PROJECT_ROOT / relative_root / "offline_tool_experience.json",
        {
            "mode": "offline_tool_experience",
            "model_called": False,
            "tool_name": tool_name,
            "arguments": arguments,
            "result": result,
            "facts": [fact.model_dump(mode="json") for fact in facts],
            "chart": chart.model_dump(mode="json") if chart else None,
        },
    )
    return OfflineToolExperience(
        session_id=session_id,
        turn_id=turn_id,
        tool_name=tool_name,
        arguments=arguments,
        result=result,
        facts=facts,
        chart=chart,
    )


def _condition_operations(outcome: AgentTurnOutcome) -> list[ConditionOperation]:
    if not outcome.tool_calls:
        return []
    final = outcome.tool_calls[-1]
    args = final.arguments
    values: dict[str, Any] = {}
    analysis_object = ANALYSIS_OBJECTS.get(final.tool_name)
    if analysis_object is not None:
        values["analysis_object"] = analysis_object
    if "period" in args:
        values["time_range"] = {
            "mode": args["period"],
            "start_date": args.get("start_date"),
            "end_date": args.get("end_date"),
        }
    if "metric" in args:
        values["metric"] = args["metric"]
    if "top_n" in args:
        values["top_n"] = args["top_n"]
    if args.get("excluded_country") is not None:
        values["filters"] = {"excluded_country": args["excluded_country"]}
    if final.tool_name == "compare_segments":
        values["comparison_objects"] = [
            "United Kingdom",
            "Outside United Kingdom",
        ]
    return [
        ConditionOperation(field=field, operation="set", value=value)
        for field, value in values.items()
    ]


def resolve_outcome_conditions(
    previous: EffectiveConditions, outcome: AgentTurnOutcome
) -> ConditionResolution:
    return resolve_conditions(previous, _condition_operations(outcome))


def compose_session_question(
    question: str,
    previous: EffectiveConditions,
    *,
    inherit_previous: bool,
) -> str:
    if not inherit_previous or previous == EffectiveConditions.empty():
        return question
    context = json.dumps(
        previous.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":")
    )
    return (
        "当前Streamlit会话的上一轮有效条件如下；本轮明确表达的条件优先，"
        "未明确修改的条件可以继承。不得直接复用历史FACT，涉及比较必须重新调用工具。\n"
        f"有效条件：{context}\n本轮原始问题保持不变：{question}"
    )


def run_online_turn(
    *,
    api_key: str,
    registry: RetailToolRegistry,
    session_id: str,
    turn_id: str,
    displayed_question: str,
    previous_conditions: EffectiveConditions,
    inherit_previous: bool,
    question_id: str | None = None,
    transport: Any | None = None,
) -> OnlineTurnExperience:
    if not api_key.strip():
        raise H4ServiceError("模型服务未配置，不能运行在线Agent。")
    session_context = compose_session_question(
        displayed_question,
        previous_conditions,
        inherit_previous=inherit_previous,
    )
    submitted = displayed_question
    relative_root = _relative_turn_root(session_id, turn_id)
    journal = ResponseEventJournal(PROJECT_ROOT / relative_root / "transport_events.jsonl")
    candidate = NativeToolOnlineCandidateClaimControllerV3_1(
        api_key=api_key,
        registry=registry,
        response_limit=MAX_RESPONSES_PER_TURN,
        model=MODEL_ID,
        transport=transport,
        real_call_confirmation=(
            "" if transport is not None else NATIVE_REAL_MODEL_CONFIRMATION
        ),
        question_count=1,
        request_timeout_seconds=120.0,
        response_event_sink=journal,
        terminal_question_ids=((question_id,) if question_id else tuple()),
    )
    if inherit_previous and session_context != displayed_question:
        candidate.client = SessionContextStrictClient(candidate.client, session_context)
    outcome = candidate.run_turn(
        session_id=session_id,
        turn_id=turn_id,
        question=submitted,
        result_root=relative_root,
    )
    for call in outcome.tool_calls:
        _save_tool_result(call)
    raw_path = f"{relative_root}/raw_responses.json"
    parsed_path = f"{relative_root}/outcome.json"
    _write_json(PROJECT_ROOT / raw_path, list(outcome.raw_responses))
    _write_json(PROJECT_ROOT / parsed_path, _outcome_payload(outcome))
    validation = None
    if (
        question_id is not None
        and not inherit_previous
        and displayed_question == load_frozen_questions()[question_id]["question"]
    ):
        validation = validate_fixed_question(question_id, outcome)
        _write_json(
            PROJECT_ROOT / relative_root / "fixed_question_validation.json",
            validation.model_dump(mode="json"),
        )
    resolution = resolve_outcome_conditions(previous_conditions, outcome)
    snapshot = candidate.response_limiter.snapshot()
    return OnlineTurnExperience(
        question_id=question_id,
        displayed_question=displayed_question,
        submitted_question=submitted,
        outcome=outcome,
        validation=validation,
        condition_resolution=resolution,
        response_limit=snapshot.limit,
        response_attempted=snapshot.attempted,
        transport_audit=candidate.transport_audit_payload(),
        trace=tuple(candidate.last_trace),
        saved_paths=(raw_path, parsed_path),
        clarification_message=(
            outcome.clarification.message
            if outcome.clarification is not None
            else None
        ),
    )


def run_chat_turn(
    *,
    api_key: str,
    registry: RetailToolRegistry,
    session_id: str,
    turn_id: str,
    question: str,
    previous_conditions: EffectiveConditions,
    inherit_previous: bool,
    clarification_answer: str | None = None,
    pending_experience: OnlineTurnExperience | None = None,
    transport: Any | None = None,
) -> OnlineTurnExperience:
    """Run or resume one general chat turn without consulting fixed QIDs."""

    if not api_key.strip():
        raise H4ServiceError("模型服务未配置，不能运行在线Agent。")
    if pending_experience is not None:
        if pending_experience.outcome.status != "needs_clarification":
            raise H4ServiceError("只有待澄清轮次可以继续。")
        if (
            pending_experience.outcome.session_id != session_id
            or pending_experience.outcome.turn_id != turn_id
            or pending_experience.displayed_question != question
        ):
            raise H4ServiceError("待澄清轮次与当前会话不一致。")
        if not clarification_answer or not clarification_answer.strip():
            raise H4ServiceError("请先填写澄清回答。")
    elif clarification_answer is not None:
        raise H4ServiceError("没有待澄清轮次，不能提交澄清回答。")

    prior_attempted = (
        pending_experience.response_attempted
        if pending_experience is not None
        else 0
    )
    remaining = MAX_CHAT_MODEL_RESPONSES - prior_attempted
    if remaining <= 0:
        raise H4ServiceError("当前轮已经达到模型响应上限。")
    relative_root = _relative_turn_root(session_id, turn_id)
    journal = ResponseEventJournal(
        PROJECT_ROOT / relative_root / "transport_events.jsonl"
    )
    runtime = NativeToolChatRuntimeV1(
        api_key=api_key,
        registry=registry,
        response_limit=remaining,
        model=MODEL_ID,
        transport=transport,
        real_call_confirmation=(
            "" if transport is not None else CHAT_REAL_MODEL_CONFIRMATION
        ),
        question_count=1,
        request_timeout_seconds=120.0,
        response_event_sink=journal,
        terminal_question_ids=tuple(),
    )
    session_context = compose_session_question(
        question,
        previous_conditions,
        inherit_previous=inherit_previous,
    )
    if inherit_previous and session_context != question:
        runtime.client = SessionContextStrictClient(runtime.client, session_context)
    outcome = runtime.run_chat_turn(
        session_id=session_id,
        turn_id=turn_id,
        question=question,
        clarification_count=1 if pending_experience is not None else 0,
        clarification_answer=(
            clarification_answer.strip() if clarification_answer else None
        ),
        result_root=relative_root,
    )
    prior_raw = (
        tuple(pending_experience.outcome.raw_responses)
        if pending_experience is not None
        else ()
    )
    combined_raw = prior_raw + tuple(outcome.raw_responses)
    attempted = prior_attempted + runtime.response_limiter.snapshot().attempted
    outcome = replace(
        outcome,
        model_response_count=attempted,
        raw_responses=combined_raw,
    )
    for call in outcome.tool_calls:
        _save_tool_result(call)
    raw_path = f"{relative_root}/raw_responses.json"
    parsed_path = f"{relative_root}/outcome.json"
    _write_json(PROJECT_ROOT / raw_path, list(combined_raw))
    _write_json(PROJECT_ROOT / parsed_path, _outcome_payload(outcome))
    resolution = resolve_outcome_conditions(previous_conditions, outcome)
    return OnlineTurnExperience(
        question_id=None,
        displayed_question=question,
        submitted_question=question,
        outcome=outcome,
        validation=None,
        condition_resolution=resolution,
        response_limit=MAX_CHAT_MODEL_RESPONSES,
        response_attempted=attempted,
        transport_audit=runtime.transport_audit_payload(),
        trace=tuple(runtime.chat_trace),
        saved_paths=(raw_path, parsed_path),
        clarification_answer=(
            clarification_answer.strip() if clarification_answer else None
        ),
        clarification_message=(
            pending_experience.outcome.clarification.message
            if pending_experience is not None
            and pending_experience.outcome.clarification is not None
            else (
                outcome.clarification.message
                if outcome.clarification is not None
                else None
            )
        ),
        runtime_kind="general_chat_v1",
    )


def _tool_call_record(call: ExecutedToolCall, question: str) -> ToolCallRecord:
    return ToolCallRecord(
        call_id=call.call_id,
        analysis_target=question[:300],
        reason_summary="模型选择该白名单工具；程序完成名称和参数Schema校验后执行。",
        tool_name=call.tool_name,
        arguments=call.arguments,
        model_selected=True,
        status="succeeded",
        result_path=call.result_path,
        error_stage=None,
        error_message=None,
    )


def _failure_record(outcome: AgentTurnOutcome, relative_root: str) -> list[FailureRecord]:
    if outcome.status != "failed":
        return []
    allowed = {
        "model_response",
        "tool_name",
        "argument_schema",
        "tool_execution",
        "fact_generation",
        "chart_generation",
        "report_validation",
    }
    stage = outcome.error_stage if outcome.error_stage in allowed else "model_response"
    return [
        FailureRecord(
            failure_id="FAIL-001",
            call_id=None,
            stage=stage,
            error_type="AgentTurnFailure",
            message=(outcome.error_message or "未提供错误信息")[:1000],
            raw_response_path=f"{relative_root}/raw_responses.json",
        )
    ]


def build_session_record(turns: list[OnlineTurnExperience]) -> SessionRunRecord:
    if not turns:
        raise H4ServiceError("当前会话没有可导出的在线Agent轮次。")
    session_id = turns[0].outcome.session_id
    now = datetime.now().astimezone().isoformat()
    records: list[TurnRunRecord] = []
    for item in turns:
        outcome = item.outcome
        relative_root = _relative_turn_root(session_id, outcome.turn_id)
        records.append(
            TurnRunRecord(
                schema_version="1.5.6-h3-turn-run-record-v1",
                session_id=session_id,
                turn_id=outcome.turn_id,
                created_at=now,
                execution_mode="online_agent",
                original_question=item.displayed_question,
                clarification_question=(
                    item.clarification_message
                ),
                clarification_answer=item.clarification_answer,
                condition_resolution=item.condition_resolution,
                tool_calls=[
                    _tool_call_record(call, item.displayed_question)
                    for call in outcome.tool_calls
                ],
                facts=list(outcome.facts),
                charts=list(outcome.charts),
                report_markdown=outcome.report_markdown,
                report_validation=outcome.report_validation,
                failures=_failure_record(outcome, relative_root),
                cross_turn_comparison=(
                    "上一轮" in item.displayed_question
                    or "此前" in item.displayed_question
                ),
                historical_fact_ids_used=[],
                raw_model_response_path=f"{relative_root}/raw_responses.json",
                parsed_tool_calls_path=f"{relative_root}/outcome.json",
                real_model_called=True,
            )
        )
    record = SessionRunRecord(
        schema_version="1.5.6-h3-session-run-record-v1",
        session_id=session_id,
        execution_mode="online_agent",
        created_at=now,
        updated_at=now,
        dataset_name="UCI Online Retail",
        dataset_id=352,
        workbook_sha256=EXPECTED_WORKBOOK_SHA256,
        metric_contract_version="1.5.6-h2-metric-contract-v1",
        model_provider=MODEL_PROVIDER,
        model_id=MODEL_ID,
        real_model_called=True,
        turns=records,
    )
    validate_record_security(record)
    return record


def _facts_csv(record: SessionRunRecord) -> str:
    buffer = io.StringIO(newline="")
    names = [
        "fact_id", "session_id", "turn_id", "call_id", "fact_type",
        "metric", "value", "display_value", "unit", "analysis_scope",
        "dimensions", "rank", "source_tool", "source_result_path",
    ]
    writer = csv.DictWriter(buffer, fieldnames=names)
    writer.writeheader()
    for turn in record.turns:
        for fact in turn.facts:
            row = fact.model_dump(mode="json")
            row.pop("schema_version")
            row["analysis_scope"] = json.dumps(row["analysis_scope"], ensure_ascii=False)
            row["dimensions"] = json.dumps(row["dimensions"], ensure_ascii=False)
            writer.writerow(row)
    return buffer.getvalue()


def build_download_zip(record: SessionRunRecord, current_turn_id: str) -> bytes:
    validate_record_security(record)
    turn = next((item for item in record.turns if item.turn_id == current_turn_id), None)
    if turn is None:
        raise H4ServiceError("找不到当前轮，不能导出。")
    payloads: dict[str, str] = {
        "run_record.json": json.dumps(
            record.model_dump(mode="json"), ensure_ascii=False, indent=2
        ) + "\n",
        "facts.csv": _facts_csv(record),
        "chart_data.json": json.dumps(
            {
                "schema_version": "1.5.6-h3-chart-export-v1",
                "session_id": record.session_id,
                "charts": [
                    chart.model_dump(mode="json")
                    for saved_turn in record.turns
                    for chart in saved_turn.charts
                ],
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
    }
    if turn.report_markdown is not None:
        payloads["business_report.md"] = turn.report_markdown
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in payloads.items():
            archive.writestr(name, value.encode("utf-8"))
    return output.getvalue()


__all__ = [
    "ANALYSIS_OBJECTS", "EXPECTED_WORKBOOK_SHA256", "H4ServiceError",
    "MAX_RESPONSES_PER_TURN", "MODEL_ID", "OfflineToolExperience",
    "OnlineTurnExperience", "TOOL_LABELS", "WORKBOOK_PATH",
    "build_download_zip", "build_real_registry", "build_session_record",
    "compose_session_question", "load_reader_contracts", "mode_policy",
    "prepare_runtime_cache", "resolve_outcome_conditions", "run_manual_tool",
    "run_chat_turn", "run_online_turn",
]
