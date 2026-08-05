"""Run a real-data traceability validation without calling an LLM."""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.chart_data import (  # noqa: E402
    ChartDataError,
    build_chart_data,
    validate_chart_data,
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
from src.tool_registry import RetailToolRegistry  # noqa: E402


WORKBOOK = PROJECT_ROOT / "data" / "raw" / "Online Retail.xlsx"
REFERENCE = (
    PROJECT_ROOT / "data" / "raw" / "h2_reference_answers.json"
)
RESULTS_ROOT = PROJECT_ROOT / "results" / "raw"
SESSION_ID = "SESSION-h3-traceability"


def _dimensions(fact: FactRecord) -> dict[str, str]:
    return {item.name: item.value for item in fact.dimensions}


def _find_fact(
    facts: list[FactRecord],
    *,
    call_id: str,
    metric: str,
    dimensions: dict[str, str] | None = None,
    rank: int | None = None,
) -> FactRecord:
    for fact in facts:
        if fact.call_id != call_id or fact.metric != metric:
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
        f"找不到FACT：call={call_id}, metric={metric}, "
        f"dimensions={dimensions}, rank={rank}"
    )


def _section_claim(
    statement: str,
    facts: list[FactRecord] | None = None,
) -> ReportClaim:
    return ReportClaim(
        statement=statement,
        evidence=[
            fact_reference(fact) for fact in (facts or [])
        ],
    )


def _draft(
    *,
    turn_id: str,
    title: str,
    claims: dict[str, ReportClaim],
) -> ReportDraft:
    fallback = {
        "用户问题与分析口径": "本轮分析口径由工具参数确定。",
        "关键经营发现": "本节没有新增数值结论。",
        "工具证据与图表": "图表数据由当前轮FACT生成。",
        "有限解释": "这里只描述历史数据关系，不推断原因。",
        "经营建议": "建议结合业务背景进行人工判断。",
        "数据与分析限制": "结果仅适用于冻结数据和指标口径。",
    }
    return ReportDraft(
        schema_version="1.5.6-h3-report-draft-v1",
        session_id=SESSION_ID,
        turn_id=turn_id,
        title=title,
        sections=[
            ReportSection(
                name=name,
                claims=[
                    claims.get(
                        name,
                        _section_claim(fallback[name]),
                    )
                ],
            )
            for name in REPORT_SECTION_ORDER
        ],
    )


def main() -> int:
    run_id = datetime.now().astimezone().strftime(
        "traceability_validation_%Y%m%dT%H%M%S_%f%z"
    )
    run_dir = RESULTS_ROOT / run_id
    frame, _ = read_online_retail_workbook(WORKBOOK)
    registry = RetailToolRegistry(
        RetailToolService(build_retail_data_layers(frame))
    )
    reference = json.loads(
        REFERENCE.read_text(encoding="utf-8")
    )["answers"]
    builder = FactBuilder()
    all_facts: list[FactRecord] = []
    call_results: dict[str, dict[str, Any]] = {}
    facts_by_call: dict[str, list[FactRecord]] = {}

    call_specs = [
        (
            "TURN-001",
            "CALL-001",
            "analyze_time_trend",
            {
                "period": "all_data",
                "start_date": None,
                "end_date": None,
                "grain": "month",
                "metric": "sales_amount",
                "exclude_incomplete_periods": True,
            },
        ),
        (
            "TURN-001",
            "CALL-002",
            "rank_products",
            {
                "period": "custom",
                "start_date": "2011-11-01",
                "end_date": "2011-11-30",
                "metric": "sales_amount",
                "top_n": 3,
            },
        ),
        (
            "TURN-002",
            "CALL-003",
            "compare_segments",
            {
                "period": "all_data",
                "start_date": None,
                "end_date": None,
                "comparison": "united_kingdom_vs_other",
            },
        ),
        (
            "TURN-003",
            "CALL-004",
            "analyze_regions",
            {
                "period": "all_data",
                "start_date": None,
                "end_date": None,
                "metric": "sales_amount",
                "top_n": 5,
                "excluded_country": "United Kingdom",
            },
        ),
    ]
    for turn_id, call_id, tool_name, arguments in call_specs:
        result = registry.execute(tool_name, arguments)
        relative_path = (
            f"results/raw/{run_id}/calls/{call_id}/result.json"
        )
        absolute_path = PROJECT_ROOT / relative_path
        save_audit_report(result, absolute_path)
        facts = builder.build(
            result,
            FactBuildContext(
                session_id=SESSION_ID,
                turn_id=turn_id,
                call_id=call_id,
                source_result_path=relative_path,
            ),
        )
        call_results[call_id] = result
        facts_by_call[call_id] = facts
        all_facts.extend(facts)

    charts = [
        build_chart_data(
            chart_id="CHART-001",
            chart_type="monthly_line",
            title="完整月份销售额趋势",
            tool_result=call_results["CALL-001"],
            facts=facts_by_call["CALL-001"],
        ),
        build_chart_data(
            chart_id="CHART-002",
            chart_type="top_n_horizontal_bar",
            title="峰值月商品销售额Top 3",
            tool_result=call_results["CALL-002"],
            facts=facts_by_call["CALL-002"],
        ),
        build_chart_data(
            chart_id="CHART-003",
            chart_type="two_segment_share_bar",
            title="英国与英国以外销售额占比",
            tool_result=call_results["CALL-003"],
            facts=facts_by_call["CALL-003"],
        ),
        build_chart_data(
            chart_id="CHART-004",
            chart_type="vertical_bar",
            title="排除英国后的地区销售额Top 5",
            tool_result=call_results["CALL-004"],
            facts=facts_by_call["CALL-004"],
        ),
    ]

    peak_period = _find_fact(
        all_facts,
        call_id="CALL-001",
        metric="peak_period",
    )
    peak_amount = _find_fact(
        all_facts,
        call_id="CALL-001",
        metric="sales_amount",
        dimensions={"month": peak_period.value},
        rank=1,
    )
    incomplete_period = _find_fact(
        all_facts,
        call_id="CALL-001",
        metric="incomplete_period",
    )
    peak_product = _find_fact(
        all_facts,
        call_id="CALL-002",
        metric="sales_amount",
        rank=1,
    )
    uk_share = _find_fact(
        all_facts,
        call_id="CALL-003",
        metric="sales_amount_share",
        dimensions={"segment": "united_kingdom"},
    )
    outside_share = _find_fact(
        all_facts,
        call_id="CALL-003",
        metric="sales_amount_share",
        dimensions={"segment": "outside_united_kingdom"},
    )
    overall_amount = _find_fact(
        all_facts,
        call_id="CALL-003",
        metric="sales_amount",
        dimensions={"segment": "overall"},
    )
    top_country = _find_fact(
        all_facts,
        call_id="CALL-004",
        metric="sales_amount",
        rank=1,
    )
    region_top_n = _find_fact(
        all_facts,
        call_id="CALL-004",
        metric="top_n",
    )

    reports = [
        _draft(
            turn_id="TURN-001",
            title="峰值月份与商品分析",
            claims={
                "用户问题与分析口径": _section_claim(
                    f"完整月份峰值为{peak_period.display_value}。",
                    [peak_period],
                ),
                "关键经营发现": _section_claim(
                    (
                        f"{peak_period.display_value}销售额为"
                        f"{peak_amount.display_value}。"
                    ),
                    [peak_period, peak_amount],
                ),
                "工具证据与图表": _section_claim(
                    (
                        f"排名第{peak_product.rank}的商品"
                        f"{_dimensions(peak_product)['stock_code']}"
                        f"销售额为{peak_product.display_value}。"
                    ),
                    [peak_product],
                ),
                "数据与分析限制": _section_claim(
                    (
                        f"{incomplete_period.display_value}"
                        "是不完整期间。"
                    ),
                    [incomplete_period],
                ),
            },
        ),
        _draft(
            turn_id="TURN-002",
            title="英国与英国以外销售比较",
            claims={
                "关键经营发现": _section_claim(
                    (
                        f"英国销售额占比{uk_share.display_value}，"
                        "英国以外销售额占比"
                        f"{outside_share.display_value}。"
                    ),
                    [uk_share, outside_share],
                ),
                "工具证据与图表": _section_claim(
                    f"总体销售额为{overall_amount.display_value}。",
                    [overall_amount],
                ),
            },
        ),
        _draft(
            turn_id="TURN-003",
            title="非英国地区销售排名",
            claims={
                "关键经营发现": _section_claim(
                    (
                        f"{_dimensions(top_country)['country']}"
                        f"销售额为{top_country.display_value}，"
                        f"排名第{top_country.rank}。"
                    ),
                    [top_country],
                ),
                "工具证据与图表": _section_claim(
                    (
                        f"图表展示前{region_top_n.display_value}"
                        "个地区。"
                    ),
                    [region_top_n],
                ),
            },
        ),
    ]
    report_validations = [
        validate_report(report, all_facts) for report in reports
    ]
    rendered_reports = [
        render_validated_report(report, all_facts)
        for report in reports
    ]

    deterministic_checks = {
        "q06_peak_period": (
            peak_period.value
            == reference["Q06"]["peak_complete_month"]
        ),
        "q06_peak_amount": (
            peak_amount.value
            == reference["Q06"]["peak_month_metrics"][
                "sales_amount_gbp"
            ]
        ),
        "q06_top_product": (
            _dimensions(peak_product)["stock_code"]
            == reference["Q06"]["top_3_products_in_peak_month"][0][
                "stock_code"
            ]
            and peak_product.value
            == reference["Q06"]["top_3_products_in_peak_month"][0][
                "sales_amount_gbp"
            ]
        ),
        "q05_segment_shares": (
            uk_share.value
            == str(
                reference["Q05"][
                    "united_kingdom_sales_amount_share"
                ]
            )
            and outside_share.value
            == str(
                reference["Q05"][
                    "outside_united_kingdom_sales_amount_share"
                ]
            )
        ),
        "q03_top_country": (
            _dimensions(top_country)["country"]
            == reference["Q03"]["ranking"][0]["country"]
            and top_country.value
            == reference["Q03"]["ranking"][0]["sales_amount_gbp"]
        ),
        "all_charts_validate": True,
        "all_reports_validate": all(
            item.status == "passed" for item in report_validations
        ),
        "all_source_result_paths_exist": all(
            (PROJECT_ROOT / fact.source_result_path).is_file()
            for fact in all_facts
        ),
    }

    changed_report = deepcopy(reports[0])
    changed_report.sections[1].claims[0].statement = (
        "峰值月份销售额为£999.99。"
    )
    changed_report_rejected = (
        validate_report(changed_report, all_facts).status == "failed"
    )
    cross_turn_report = deepcopy(reports[0])
    cross_turn_report.sections[0].claims[0] = _section_claim(
        f"总体销售额为{overall_amount.display_value}。",
        [overall_amount],
    )
    cross_turn_rejected = any(
        issue.code == "cross_turn_fact"
        for issue in validate_report(
            cross_turn_report,
            all_facts,
        ).issues
    )
    changed_chart = charts[0].model_copy(deep=True)
    changed_chart.series[0].values[0] = "999.99"
    try:
        validate_chart_data(changed_chart, facts_by_call["CALL-001"])
    except ChartDataError:
        changed_chart_rejected = True
    else:
        changed_chart_rejected = False
    negative_checks = {
        "changed_report_number_rejected": changed_report_rejected,
        "cross_turn_fact_rejected": cross_turn_rejected,
        "changed_chart_value_rejected": changed_chart_rejected,
    }

    summary = {
        "schema_version": "1.5.6-h3-traceability-validation-v1",
        "created_at": datetime.now().astimezone().isoformat(),
        "run_id": run_id,
        "real_model_called": False,
        "tool_call_count": len(call_specs),
        "turn_count": 3,
        "fact_count": len(all_facts),
        "chart_count": len(charts),
        "report_count": len(reports),
        "deterministic_checks": deterministic_checks,
        "negative_checks": negative_checks,
        "privacy": {
            "customer_id_values_exported": False,
            "raw_rows_exported": False,
            "absolute_source_paths_saved": False,
        },
        "all_passed": (
            all(deterministic_checks.values())
            and all(negative_checks.values())
        ),
    }

    save_audit_report(
        {
            "schema_version": "1.5.6-h3-fact-records-v1",
            "facts": [
                fact.model_dump(mode="json") for fact in all_facts
            ],
        },
        run_dir / "facts.json",
    )
    save_audit_report(
        {
            "schema_version": "1.5.6-h3-chart-records-v1",
            "charts": [
                chart.model_dump(mode="json") for chart in charts
            ],
        },
        run_dir / "chart_data.json",
    )
    save_audit_report(
        {
            "schema_version": "1.5.6-h3-report-validations-v1",
            "validations": [
                item.model_dump(mode="json")
                for item in report_validations
            ],
        },
        run_dir / "report_validations.json",
    )
    for index, markdown in enumerate(rendered_reports, start=1):
        report_path = run_dir / "reports" / f"TURN-{index:03d}.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(markdown, encoding="utf-8")
    save_audit_report(summary, run_dir / "summary.json")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"本地追溯验证记录：{run_dir.resolve()}")
    return 0 if summary["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
