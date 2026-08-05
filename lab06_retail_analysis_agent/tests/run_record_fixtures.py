from __future__ import annotations

from src.chart_data import build_chart_data
from src.conversation_state import (
    ConditionOperation,
    EffectiveConditions,
    resolve_conditions,
)
from src.fact_builder import FactBuildContext, FactBuilder
from src.report_validation import (
    REPORT_SECTION_ORDER,
    ReportClaim,
    ReportDraft,
    ReportSection,
    fact_reference,
    render_validated_report,
    validate_report,
)
from src.retail_cleaning import build_retail_data_layers
from src.retail_tools import RetailToolService
from src.run_record import (
    SessionRunRecord,
    ToolCallRecord,
    TurnRunRecord,
)
from src.tool_registry import RetailToolRegistry
from tests.test_retail_cleaning import sample_frame


def build_sample_session_record() -> SessionRunRecord:
    layers = build_retail_data_layers(sample_frame())
    registry = RetailToolRegistry(RetailToolService(layers))
    result = registry.execute(
        "rank_products",
        {
            "period": "all_data",
            "start_date": None,
            "end_date": None,
            "metric": "sales_amount",
            "top_n": 1,
        },
    )
    result_path = "results/raw/test/CALL-001/result.json"
    facts = FactBuilder().build(
        result,
        FactBuildContext(
            session_id="SESSION-test",
            turn_id="TURN-001",
            call_id="CALL-001",
            source_result_path=result_path,
        ),
    )
    chart = build_chart_data(
        chart_id="CHART-001",
        chart_type="top_n_horizontal_bar",
        title="商品销售额排名",
        tool_result=result,
        facts=facts,
    )
    amount_fact = next(
        fact for fact in facts if fact.metric == "sales_amount"
    )
    sections = []
    for name in REPORT_SECTION_ORDER:
        if name == "关键经营发现":
            claim = ReportClaim(
                statement=(
                    f"排名第{amount_fact.rank}的商品销售额为"
                    f"{amount_fact.display_value}。"
                ),
                evidence=[fact_reference(amount_fact)],
            )
        else:
            claim = ReportClaim(
                statement="本节没有新增数值结论。",
                evidence=[],
            )
        sections.append(ReportSection(name=name, claims=[claim]))
    draft = ReportDraft(
        schema_version="1.5.6-h3-report-draft-v1",
        session_id="SESSION-test",
        turn_id="TURN-001",
        title="测试报告",
        sections=sections,
    )
    validation = validate_report(draft, facts)
    report = render_validated_report(draft, facts)
    conditions = resolve_conditions(
        EffectiveConditions.empty(),
        [
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
                value=1,
            ),
        ],
    )
    turn = TurnRunRecord(
        schema_version="1.5.6-h3-turn-run-record-v1",
        session_id="SESSION-test",
        turn_id="TURN-001",
        created_at="2026-07-31T01:00:00+08:00",
        execution_mode="deterministic_validation",
        original_question="验证商品销售额排名。",
        clarification_question=None,
        clarification_answer=None,
        condition_resolution=conditions,
        tool_calls=[
            ToolCallRecord(
                call_id="CALL-001",
                analysis_target="商品销售额排名",
                reason_summary="验证白名单工具、FACT和图表追溯。",
                tool_name="rank_products",
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
        report_markdown=report,
        report_validation=validation,
        failures=[],
        cross_turn_comparison=False,
        historical_fact_ids_used=[],
        raw_model_response_path=None,
        parsed_tool_calls_path=None,
        real_model_called=False,
    )
    return SessionRunRecord(
        schema_version="1.5.6-h3-session-run-record-v1",
        session_id="SESSION-test",
        execution_mode="deterministic_validation",
        created_at="2026-07-31T01:00:00+08:00",
        updated_at="2026-07-31T01:00:01+08:00",
        dataset_name="UCI Online Retail",
        dataset_id=352,
        workbook_sha256=(
            "43465a06f2ccf7c8b5bd2892bc7defb52f97487934fe93b16"
            "ae4c3936424676d"
        ),
        metric_contract_version="1.5.6-h2-metric-contract-v1",
        model_provider=None,
        model_id=None,
        real_model_called=False,
        turns=[turn],
    )
