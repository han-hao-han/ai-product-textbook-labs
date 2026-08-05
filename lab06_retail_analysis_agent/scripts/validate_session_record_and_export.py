"""Validate multi-turn state, run records, offline mode and exports."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.chart_data import build_chart_data  # noqa: E402
from src.conversation_state import (  # noqa: E402
    ConditionOperation,
    ConditionResolution,
    EffectiveConditions,
    resolve_conditions,
)
from src.data_audit import (  # noqa: E402
    read_online_retail_workbook,
    save_audit_report,
)
from src.fact_builder import (  # noqa: E402
    FactBuildContext,
    FactBuilder,
)
from src.fact_schema import FactRecord  # noqa: E402
from src.offline_mode import (  # noqa: E402
    CapabilityDeniedError,
    build_mode_policy,
    require_capability,
)
from src.report_validation import (  # noqa: E402
    REPORT_SECTION_ORDER,
    ReportClaim,
    ReportDraft,
    ReportSection,
    fact_reference,
    render_validated_report,
    validate_report,
)
from src.retail_cleaning import build_retail_data_layers  # noqa: E402
from src.retail_tools import RetailToolService  # noqa: E402
from src.run_record import (  # noqa: E402
    SessionRunRecord,
    ToolCallRecord,
    TurnRunRecord,
    load_session_run_record,
    save_session_run_record,
    validate_record_security,
)
from src.safe_export import (  # noqa: E402
    EXPORT_FILENAMES,
    export_session_bundle,
)
from src.tool_registry import RetailToolRegistry  # noqa: E402


WORKBOOK = PROJECT_ROOT / "data" / "raw" / "Online Retail.xlsx"
REFERENCE = (
    PROJECT_ROOT / "data" / "raw" / "h2_reference_answers.json"
)
RESULTS_ROOT = PROJECT_ROOT / "results" / "raw"
SESSION_ID = "SESSION-h3-multi-turn"
OFFLINE_SESSION_ID = "SESSION-h3-offline"
WORKBOOK_SHA256 = (
    "43465a06f2ccf7c8b5bd2892bc7defb52f97487934fe93b16"
    "ae4c3936424676d"
)


def _dimensions(fact: FactRecord) -> dict[str, str]:
    return {item.name: item.value for item in fact.dimensions}


def _find_fact(
    facts: list[FactRecord],
    *,
    metric: str,
    rank: int | None = None,
    dimensions: dict[str, str] | None = None,
) -> FactRecord:
    for fact in facts:
        if fact.metric != metric:
            continue
        if rank is not None and fact.rank != rank:
            continue
        actual_dimensions = _dimensions(fact)
        if dimensions and any(
            actual_dimensions.get(key) != value
            for key, value in dimensions.items()
        ):
            continue
        return fact
    raise KeyError(
        f"找不到FACT：metric={metric}, rank={rank}, "
        f"dimensions={dimensions}"
    )


def _claim(
    statement: str,
    facts: list[FactRecord] | None = None,
) -> ReportClaim:
    return ReportClaim(
        statement=statement,
        evidence=[
            fact_reference(fact) for fact in (facts or [])
        ],
    )


def _condition_statuses(
    resolution: ConditionResolution,
) -> dict[str, str]:
    return {
        change.field: change.status for change in resolution.changes
    }


def _make_session_record(
    *,
    now: str,
    turns: list[TurnRunRecord],
) -> SessionRunRecord:
    return SessionRunRecord(
        schema_version="1.5.6-h3-session-run-record-v1",
        session_id=SESSION_ID,
        execution_mode="deterministic_validation",
        created_at=now,
        updated_at=now,
        dataset_name="UCI Online Retail",
        dataset_id=352,
        workbook_sha256=WORKBOOK_SHA256,
        metric_contract_version="1.5.6-h2-metric-contract-v1",
        model_provider=None,
        model_id=None,
        real_model_called=False,
        turns=turns,
    )


def main() -> int:
    now = datetime.now().astimezone()
    run_id = now.strftime(
        "session_validation_%Y%m%dT%H%M%S_%f%z"
    )
    created_at = now.isoformat()
    run_dir = RESULTS_ROOT / run_id
    reference = json.loads(
        REFERENCE.read_text(encoding="utf-8")
    )["answers"]
    frame, _ = read_online_retail_workbook(WORKBOOK)
    registry = RetailToolRegistry(
        RetailToolService(build_retail_data_layers(frame))
    )
    fact_builder = FactBuilder()
    previous = EffectiveConditions.empty()
    turns: list[TurnRunRecord] = []

    turn_specs = [
        {
            "turn_id": "TURN-001",
            "call_id": "CALL-001",
            "question": "查看2011年11月销售额最高的前3个商品。",
            "operations": [
                ConditionOperation(
                    field="time_range",
                    operation="set",
                    value={
                        "mode": "custom",
                        "start_date": "2011-11-01",
                        "end_date": "2011-11-30",
                    },
                ),
                ConditionOperation(
                    field="metric",
                    operation="set",
                    value="sales_amount",
                ),
                ConditionOperation(
                    field="analysis_object",
                    operation="set",
                    value="product",
                ),
                ConditionOperation(
                    field="top_n",
                    operation="set",
                    value=3,
                ),
            ],
            "tool": "rank_products",
            "arguments": {
                "period": "custom",
                "start_date": "2011-11-01",
                "end_date": "2011-11-30",
                "metric": "sales_amount",
                "top_n": 3,
            },
            "chart_type": "top_n_horizontal_bar",
            "chart_title": "2011年11月商品销售额Top 3",
            "cross_turn": False,
        },
        {
            "turn_id": "TURN-002",
            "call_id": "CALL-002",
            "question": "改成全部数据，排除英国，查看前5个地区。",
            "operations": [
                ConditionOperation(
                    field="time_range",
                    operation="set",
                    value={
                        "mode": "all_data",
                        "start_date": None,
                        "end_date": None,
                    },
                ),
                ConditionOperation(
                    field="analysis_object",
                    operation="set",
                    value="region",
                ),
                ConditionOperation(
                    field="top_n",
                    operation="set",
                    value=5,
                ),
                ConditionOperation(
                    field="filters",
                    operation="set",
                    value={"excluded_country": "United Kingdom"},
                ),
            ],
            "tool": "analyze_regions",
            "arguments": {
                "period": "all_data",
                "start_date": None,
                "end_date": None,
                "metric": "sales_amount",
                "top_n": 5,
                "excluded_country": "United Kingdom",
            },
            "chart_type": "vertical_bar",
            "chart_title": "排除英国后的地区销售额Top 5",
            "cross_turn": False,
        },
        {
            "turn_id": "TURN-003",
            "call_id": "CALL-003",
            "question": "取消地区筛选和前5限制，比较英国与英国以外。",
            "operations": [
                ConditionOperation(
                    field="analysis_object",
                    operation="set",
                    value="segments",
                ),
                ConditionOperation(
                    field="comparison_objects",
                    operation="set",
                    value=[
                        "united_kingdom",
                        "outside_united_kingdom",
                    ],
                ),
                ConditionOperation(
                    field="filters",
                    operation="remove",
                    value=None,
                ),
                ConditionOperation(
                    field="top_n",
                    operation="remove",
                    value=None,
                ),
            ],
            "tool": "compare_segments",
            "arguments": {
                "period": "all_data",
                "start_date": None,
                "end_date": None,
                "comparison": "united_kingdom_vs_other",
            },
            "chart_type": "two_segment_share_bar",
            "chart_title": "英国与英国以外销售额占比",
            "cross_turn": True,
        },
    ]

    turn_artifacts: dict[str, dict[str, Any]] = {}
    for index, spec in enumerate(turn_specs, start=1):
        resolution = resolve_conditions(
            previous,
            spec["operations"],
        )
        previous = resolution.effective
        result = registry.execute(spec["tool"], spec["arguments"])
        result_path = (
            f"results/raw/{run_id}/calls/"
            f"{spec['call_id']}/result.json"
        )
        save_audit_report(result, PROJECT_ROOT / result_path)
        facts = fact_builder.build(
            result,
            FactBuildContext(
                session_id=SESSION_ID,
                turn_id=spec["turn_id"],
                call_id=spec["call_id"],
                source_result_path=result_path,
            ),
        )
        chart = build_chart_data(
            chart_id=f"CHART-{index:03d}",
            chart_type=spec["chart_type"],
            title=spec["chart_title"],
            tool_result=result,
            facts=facts,
        )
        primary_fact = _find_fact(
            facts,
            metric="sales_amount_share"
            if spec["tool"] == "compare_segments"
            else "sales_amount",
            rank=1
            if spec["tool"] != "compare_segments"
            else None,
            dimensions=(
                {"segment": "united_kingdom"}
                if spec["tool"] == "compare_segments"
                else None
            ),
        )
        if spec["tool"] == "rank_products":
            statement = (
                f"排名第{primary_fact.rank}的商品"
                f"{_dimensions(primary_fact)['stock_code']}"
                f"销售额为{primary_fact.display_value}。"
            )
        elif spec["tool"] == "analyze_regions":
            statement = (
                f"{_dimensions(primary_fact)['country']}销售额为"
                f"{primary_fact.display_value}，"
                f"排名第{primary_fact.rank}。"
            )
        else:
            outside_fact = _find_fact(
                facts,
                metric="sales_amount_share",
                dimensions={
                    "segment": "outside_united_kingdom"
                },
            )
            statement = (
                f"英国销售额占比{primary_fact.display_value}，"
                "英国以外销售额占比"
                f"{outside_fact.display_value}。"
            )
        sections = []
        for name in REPORT_SECTION_ORDER:
            if name == "关键经营发现":
                evidence = [primary_fact]
                if spec["tool"] == "compare_segments":
                    evidence.append(outside_fact)
                claim = _claim(statement, evidence)
            else:
                claim = _claim(
                    {
                        "用户问题与分析口径": (
                            "本轮分析使用界面展示的有效条件。"
                        ),
                        "工具证据与图表": (
                            "图表只使用当前轮同一CALL的FACT。"
                        ),
                        "有限解释": (
                            "结果只描述冻结数据中的历史关系。"
                        ),
                        "经营建议": (
                            "建议结合业务背景进行人工判断。"
                        ),
                        "数据与分析限制": (
                            "不支持利润、预测或因果结论。"
                        ),
                    }[name]
                )
            sections.append(ReportSection(name=name, claims=[claim]))
        draft = ReportDraft(
            schema_version="1.5.6-h3-report-draft-v1",
            session_id=SESSION_ID,
            turn_id=spec["turn_id"],
            title=f"{spec['turn_id']}经营分析报告",
            sections=sections,
        )
        report_validation = validate_report(draft, facts)
        report_markdown = render_validated_report(draft, facts)
        turn = TurnRunRecord(
            schema_version="1.5.6-h3-turn-run-record-v1",
            session_id=SESSION_ID,
            turn_id=spec["turn_id"],
            created_at=created_at,
            execution_mode="deterministic_validation",
            original_question=spec["question"],
            clarification_question=None,
            clarification_answer=None,
            condition_resolution=resolution,
            tool_calls=[
                ToolCallRecord(
                    call_id=spec["call_id"],
                    analysis_target=spec["question"],
                    reason_summary=(
                        "确定性验证当前轮有效条件和重新计算。"
                    ),
                    tool_name=spec["tool"],
                    arguments=result["arguments"],
                    model_selected=False,
                    status="succeeded",
                    result_path=result_path,
                    error_stage=None,
                    error_message=None,
                )
            ],
            facts=facts,
            charts=[chart],
            report_markdown=report_markdown,
            report_validation=report_validation,
            failures=[],
            cross_turn_comparison=spec["cross_turn"],
            historical_fact_ids_used=[],
            raw_model_response_path=None,
            parsed_tool_calls_path=None,
            real_model_called=False,
        )
        turns.append(turn)
        turn_artifacts[spec["turn_id"]] = {
            "facts": facts,
            "resolution": resolution,
            "primary_fact": primary_fact,
        }

    session = _make_session_record(now=created_at, turns=turns)
    record_path = run_dir / "run_record.local.json"
    save_session_run_record(session, record_path)
    loaded = load_session_run_record(record_path)
    export_paths = export_session_bundle(
        loaded,
        run_dir / "export",
        current_turn_id="TURN-003",
    )
    imported = load_session_run_record(export_paths[0])

    offline_policy = build_mode_policy(api_key_configured=False)
    require_capability(
        offline_policy,
        "run_manual_whitelist_tool",
    )
    try:
        require_capability(
            offline_policy,
            "model_tool_selection",
        )
    except CapabilityDeniedError:
        offline_agent_capability_rejected = True
    else:
        offline_agent_capability_rejected = False

    offline_result = registry.execute(
        "get_data_profile",
        {"section": "summary"},
    )
    offline_result_path = (
        f"results/raw/{run_id}/offline/CALL-001/result.json"
    )
    save_audit_report(
        offline_result,
        PROJECT_ROOT / offline_result_path,
    )
    offline_facts = FactBuilder().build(
        offline_result,
        FactBuildContext(
            session_id=OFFLINE_SESSION_ID,
            turn_id="TURN-001",
            call_id="CALL-001",
            source_result_path=offline_result_path,
        ),
    )
    offline_conditions = resolve_conditions(
        EffectiveConditions.empty(),
        [],
    )
    offline_turn = TurnRunRecord(
        schema_version="1.5.6-h3-turn-run-record-v1",
        session_id=OFFLINE_SESSION_ID,
        turn_id="TURN-001",
        created_at=created_at,
        execution_mode="offline_tool_experience",
        original_question="手动查看固定数据概况。",
        clarification_question=None,
        clarification_answer=None,
        condition_resolution=offline_conditions,
        tool_calls=[
            ToolCallRecord(
                call_id="CALL-001",
                analysis_target="查看固定数据概况",
                reason_summary="读者手动选择白名单工具。",
                tool_name="get_data_profile",
                arguments=offline_result["arguments"],
                model_selected=False,
                status="succeeded",
                result_path=offline_result_path,
                error_stage=None,
                error_message=None,
            )
        ],
        facts=offline_facts,
        charts=[],
        report_markdown=None,
        report_validation=None,
        failures=[],
        cross_turn_comparison=False,
        historical_fact_ids_used=[],
        raw_model_response_path=None,
        parsed_tool_calls_path=None,
        real_model_called=False,
    )
    offline_session = SessionRunRecord(
        schema_version="1.5.6-h3-session-run-record-v1",
        session_id=OFFLINE_SESSION_ID,
        execution_mode="offline_tool_experience",
        created_at=created_at,
        updated_at=created_at,
        dataset_name="UCI Online Retail",
        dataset_id=352,
        workbook_sha256=WORKBOOK_SHA256,
        metric_contract_version="1.5.6-h2-metric-contract-v1",
        model_provider=None,
        model_id=None,
        real_model_called=False,
        turns=[offline_turn],
    )
    save_session_run_record(
        offline_session,
        run_dir / "offline_run_record.local.json",
    )

    turn1_fact = turn_artifacts["TURN-001"]["primary_fact"]
    turn2_fact = turn_artifacts["TURN-002"]["primary_fact"]
    turn3_fact = turn_artifacts["TURN-003"]["primary_fact"]
    turn2_statuses = _condition_statuses(
        turn_artifacts["TURN-002"]["resolution"]
    )
    turn3_statuses = _condition_statuses(
        turn_artifacts["TURN-003"]["resolution"]
    )
    checks = {
        "turn1_matches_h2_peak_month_top_product": (
            _dimensions(turn1_fact)["stock_code"]
            == reference["Q06"]["top_3_products_in_peak_month"][0][
                "stock_code"
            ]
            and turn1_fact.value
            == reference["Q06"]["top_3_products_in_peak_month"][0][
                "sales_amount_gbp"
            ]
        ),
        "turn2_matches_h2_non_uk_top_country": (
            _dimensions(turn2_fact)["country"]
            == reference["Q03"]["ranking"][0]["country"]
            and turn2_fact.value
            == reference["Q03"]["ranking"][0]["sales_amount_gbp"]
        ),
        "turn3_matches_h2_uk_share": (
            turn3_fact.value
            == str(
                reference["Q05"][
                    "united_kingdom_sales_amount_share"
                ]
            )
        ),
        "turn2_change_labels": (
            turn2_statuses["time_range"] == "modified"
            and turn2_statuses["metric"] == "inherited"
            and turn2_statuses["analysis_object"] == "modified"
            and turn2_statuses["filters"] == "added"
            and turn2_statuses["top_n"] == "modified"
        ),
        "turn3_change_labels": (
            turn3_statuses["time_range"] == "inherited"
            and turn3_statuses["metric"] == "inherited"
            and turn3_statuses["analysis_object"] == "modified"
            and turn3_statuses["comparison_objects"] == "added"
            and turn3_statuses["filters"] == "removed"
            and turn3_statuses["top_n"] == "removed"
        ),
        "cross_turn_comparison_recomputed": (
            turns[2].cross_turn_comparison
            and len(turns[2].tool_calls) == 1
            and turns[2].historical_fact_ids_used == []
            and all(
                fact.turn_id == "TURN-003"
                for fact in turns[2].facts
            )
        ),
        "historical_reports_not_merged": all(
            earlier.report_markdown not in turns[2].report_markdown
            for earlier in turns[:2]
        ),
        "record_round_trip": loaded == session,
        "export_import_round_trip": imported == session,
        "four_file_export": (
            tuple(path.name for path in export_paths)
            == EXPORT_FILENAMES
            and all(path.is_file() for path in export_paths)
        ),
        "record_security_passed": True,
        "offline_manual_tool_allowed": True,
        "offline_agent_capability_rejected": (
            offline_agent_capability_rejected
        ),
        "offline_record_has_no_agent_or_report": (
            not offline_session.real_model_called
            and offline_turn.report_markdown is None
            and not offline_turn.tool_calls[0].model_selected
        ),
    }
    validate_record_security(session)
    validate_record_security(offline_session)

    bad_turn_payload = turns[2].model_dump(mode="json")
    bad_turn_payload["tool_calls"] = []
    try:
        TurnRunRecord.model_validate(bad_turn_payload)
    except ValidationError:
        cross_turn_without_new_call_rejected = True
    else:
        cross_turn_without_new_call_rejected = False
    negative_checks = {
        "cross_turn_without_new_call_rejected": (
            cross_turn_without_new_call_rejected
        )
    }
    summary = {
        "schema_version": "1.5.6-h3-session-validation-v1",
        "created_at": created_at,
        "run_id": run_id,
        "real_model_called": False,
        "session_turn_count": len(turns),
        "tool_call_count": sum(
            len(turn.tool_calls) for turn in turns
        ),
        "fact_count": sum(len(turn.facts) for turn in turns),
        "chart_count": sum(len(turn.charts) for turn in turns),
        "report_count": sum(
            turn.report_markdown is not None for turn in turns
        ),
        "export_files": [path.name for path in export_paths],
        "checks": checks,
        "negative_checks": negative_checks,
        "privacy": {
            "customer_id_values_exported": False,
            "raw_rows_exported": False,
            "api_key_or_authorization_saved": False,
            "absolute_paths_saved": False,
        },
        "all_passed": (
            all(checks.values())
            and all(negative_checks.values())
        ),
    }
    save_audit_report(summary, run_dir / "summary.json")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"本地会话验证记录：{run_dir.resolve()}")
    return 0 if summary["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
