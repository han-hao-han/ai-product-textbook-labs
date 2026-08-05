"""Replay the V2 report boundary against FACTs from a saved real run.

This script never calls a model. It creates a numeric-free report plan,
validates its FACT references, and lets the program inject canonical values.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.fact_schema import FactRecord  # noqa: E402
from src.report_finalization_v2 import (  # noqa: E402
    ChartRequestV2,
    FinalReportResponseV2,
    ReportClaimPlanV2,
    ReportPlanV2,
    ReportSectionPlanV2,
    finalize_report_v2,
    render_finalized_report_v2,
    validate_report_plan_v2,
)
from src.report_validation import REPORT_SECTION_ORDER  # noqa: E402


KIND_BY_SECTION = {
    "用户问题与分析口径": "scope",
    "关键经营发现": "finding",
    "工具证据与图表": "evidence_note",
    "有限解释": "limited_interpretation",
    "经营建议": "recommendation",
    "数据与分析限制": "limitation",
}
NARRATIVE_BY_KIND = {
    "scope": "分析采用冻结的完整月份与正常销售事实口径。",
    "finding": "程序证据显示峰值月份及其商品表现存在明确排序。",
    "evidence_note": "当前轮工具事实共同支持上述描述性发现。",
    "limited_interpretation": "这些事实只能说明已观察到的经营表现，不能证明原因。",
    "recommendation": "建议结合成本、库存与活动信息开展后续人工评估。",
    "limitation": "当前数据不能支持利润、因果、预测或自动补货判断。",
}


def _dimension_value(fact: FactRecord, name: str) -> str | None:
    return next(
        (
            dimension.value
            for dimension in fact.dimensions
            if dimension.name == name
        ),
        None,
    )


def select_q06_facts(facts: list[FactRecord]) -> list[FactRecord]:
    peak = next(
        fact for fact in facts if fact.metric == "peak_period"
    )
    peak_month = peak.value
    peak_sales = next(
        fact
        for fact in facts
        if (
            fact.source_tool == "analyze_time_trend"
            and fact.metric == "sales_amount"
            and _dimension_value(fact, "month") == peak_month
        )
    )
    product_sales = sorted(
        (
            fact
            for fact in facts
            if (
                fact.source_tool == "rank_products"
                and fact.metric == "sales_amount"
                and fact.rank is not None
            )
        ),
        key=lambda fact: fact.rank or 0,
    )
    if not product_sales:
        raise ValueError("真实记录中没有商品销售额排名FACT")
    return [peak, peak_sales, *product_sales]


def build_q06_plan(
    *,
    session_id: str,
    turn_id: str,
    facts: list[FactRecord],
) -> FinalReportResponseV2:
    selected = select_q06_facts(facts)
    fact_ids = [fact.fact_id for fact in selected]
    sections = []
    for name in REPORT_SECTION_ORDER:
        kind = KIND_BY_SECTION[name]
        sections.append(
            ReportSectionPlanV2(
                name=name,
                claims=[
                    ReportClaimPlanV2(
                        claim_kind=kind,
                        narrative=NARRATIVE_BY_KIND[kind],
                        fact_ids=(
                            []
                            if kind in {"scope", "limitation"}
                            else fact_ids
                        ),
                    )
                ],
            )
        )
    rank_call_id = next(
        fact.call_id
        for fact in selected
        if fact.source_tool == "rank_products"
    )
    return FinalReportResponseV2(
        response_type="report",
        report=ReportPlanV2(
            schema_version="1.5.6-h3-report-plan-v2",
            session_id=session_id,
            turn_id=turn_id,
            title="完整月份峰值与商品表现",
            sections=sections,
        ),
        chart_requests=[
            ChartRequestV2(
                call_id=rank_call_id,
                chart_type="top_n_horizontal_bar",
                title="峰值期间商品销售额排序",
            )
        ],
    )


def _find_turn(
    record: dict[str, Any],
    turn_id: str,
) -> dict[str, Any]:
    return next(
        turn
        for turn in record["turns"]
        if turn["turn_id"] == turn_id
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-record", type=Path, required=True)
    parser.add_argument("--turn-id", default="TURN-001")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    record = json.loads(
        args.session_record.read_text(encoding="utf-8")
    )
    turn = _find_turn(record, args.turn_id)
    facts = [
        FactRecord.model_validate(item) for item in turn["facts"]
    ]
    response = build_q06_plan(
        session_id=record["session_id"],
        turn_id=args.turn_id,
        facts=facts,
    )
    validation = validate_report_plan_v2(response, facts)
    if validation.status != "passed":
        raise ValueError(
            "离线回放失败："
            + "、".join(issue.code for issue in validation.issues)
        )
    finalized = finalize_report_v2(response, facts)
    markdown = render_finalized_report_v2(finalized)

    timestamp = datetime.now().astimezone().strftime(
        "%Y%m%dT%H%M%S_%f%z"
    )
    output_dir = args.output_dir or (
        Path("results/raw") / f"report_v2_replay_{timestamp}"
    )
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "report_plan.json").write_text(
        response.model_dump_json(indent=2),
        encoding="utf-8",
    )
    (output_dir / "validation.json").write_text(
        validation.model_dump_json(indent=2),
        encoding="utf-8",
    )
    (output_dir / "finalized_report.json").write_text(
        finalized.model_dump_json(indent=2),
        encoding="utf-8",
    )
    (output_dir / "report.md").write_text(
        markdown,
        encoding="utf-8",
    )
    summary = {
        "schema_version": "1.5.6-h3-report-v2-replay-v1",
        "execution_mode": "offline_replay",
        "real_model_called": False,
        "source_session_id": record["session_id"],
        "source_turn_id": args.turn_id,
        "source_fact_count": len(facts),
        "selected_fact_ids": finalized.referenced_fact_ids,
        "validation_status": validation.status,
        "output_dir": output_dir.as_posix(),
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
