"""Export the frozen FACT, chart-data and report traceability contract."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.chart_data import (  # noqa: E402
    CHART_SOURCE_TOOLS,
    ChartData,
)
from src.fact_schema import FactRecord  # noqa: E402
from src.report_validation import (  # noqa: E402
    REPORT_SECTION_ORDER,
    ReportDraft,
    ReportValidationResult,
)


DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "config"
    / "h3_fact_chart_report_contract.json"
)


def build_contract() -> dict[str, object]:
    return {
        "schema_version": (
            "1.5.6-h3-fact-chart-report-contract-v1"
        ),
        "status": "frozen_by_user",
        "frozen_on": "2026-07-31",
        "v2_2_2_additive_extension": {
            "status": "frozen_by_user_offline_validated",
            "added_on": "2026-08-03",
            "report_validation_result_adds_manual_review_flags": True,
            "manual_flags_change_deterministic_status": False,
            "report_draft_schema_changed": False,
            "fact_schema_changed": False,
        },
        "acceptance_harness_six_boundary_extension": {
            "status": "frozen_by_user_implemented_offline",
            "implemented_on": "2026-08-03",
            "report_evidence_source_types": [
                "FACT",
                "REQUEST",
                "POLICY",
            ],
            "rank_only_on_selected_metric_fact": True,
            "report_draft_evidence_union_changed": True,
            "fact_schema_changed": False,
            "h2_reference_answers_changed": False,
        },
        "h2_dependencies_must_remain_frozen": True,
        "fact": {
            "schema": FactRecord.model_json_schema(),
            "id_scope": "session内单调递增，格式FACT-<三位以上序号>",
            "value_policy": {
                "value": "工具结果的规范化原值字符串",
                "display_value": "程序按冻结单位生成的展示值",
                "model_may_calculate_or_convert": False,
            },
            "privacy": {
                "customer_id_dimension_allowed": False,
                "absolute_source_path_allowed": False,
            },
        },
        "chart_data": {
            "schema": ChartData.model_json_schema(),
            "whitelist_source_tools": CHART_SOURCE_TOOLS,
            "single_call_only": True,
            "model_generated_chart_code_allowed": False,
        },
        "report": {
            "draft_schema": ReportDraft.model_json_schema(),
            "validation_schema": (
                ReportValidationResult.model_json_schema()
            ),
            "sections": list(REPORT_SECTION_ORDER),
            "citation_rendering": (
                "模型提交结构化evidence，程序校验后追加"
                "[FACT-nnn]、[REQUEST-nnn]或[POLICY-nnn]"
            ),
            "deterministic_checks": [
                "FACT存在且属于当前会话轮次",
                "规范值与展示值一致",
                "单位一致",
                "时间范围一致",
                "排名一致",
                "日期等价规范化后，报告数值与期间均可追溯",
                "明确语义断言有当前claim的FACT能力支持",
                "固定问题报告完整性逐项绑定FACT、REQUEST或POLICY",
            ],
            "manual_review_required": [
                "季节性解释",
                "库存行动",
                "定价或物流行动",
                "因果或效果暗示",
                "普通显著、高客单价和走量型分类",
            ],
        },
        "change_control": (
            "用户冻结后，修改FACT字段、图表类型、报告章节或校验规则"
            "必须重新确认。"
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="导出已冻结的FACT、图表数据和报告追溯契约。"
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(build_contract(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"已导出冻结契约：{output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
