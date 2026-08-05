"""Create the frozen four-file, privacy-checked run export bundle."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from src.run_record import (
    RunRecordError,
    SessionRunRecord,
    scan_sensitive_content,
    validate_record_security,
)


EXPORT_FILENAMES = (
    "run_record.json",
    "business_report.md",
    "facts.csv",
    "chart_data.json",
)


def _ensure_safe_text(text: str, label: str) -> None:
    issues = scan_sensitive_content(text)
    if issues:
        raise RunRecordError(
            f"{label}导出安全检查失败：" + "；".join(issues)
        )


def _write_new_text(path: Path, text: str) -> None:
    if path.exists():
        raise RunRecordError(f"导出目标已存在，不覆盖：{path.name}")
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _facts_csv(record: SessionRunRecord) -> str:
    output = io.StringIO(newline="")
    fieldnames = [
        "fact_id",
        "session_id",
        "turn_id",
        "call_id",
        "fact_type",
        "metric",
        "value",
        "display_value",
        "unit",
        "analysis_scope",
        "dimensions",
        "rank",
        "source_tool",
        "source_result_path",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for turn in record.turns:
        for fact in turn.facts:
            payload = fact.model_dump(mode="json")
            payload.pop("schema_version")
            payload["analysis_scope"] = json.dumps(
                payload["analysis_scope"],
                ensure_ascii=False,
                separators=(",", ":"),
            )
            payload["dimensions"] = json.dumps(
                payload["dimensions"],
                ensure_ascii=False,
                separators=(",", ":"),
            )
            writer.writerow(payload)
    return output.getvalue()


def export_session_bundle(
    record: SessionRunRecord,
    output_dir: Path,
    *,
    current_turn_id: str,
) -> tuple[Path, ...]:
    validate_record_security(record)
    current_turn = next(
        (
            turn
            for turn in record.turns
            if turn.turn_id == current_turn_id
        ),
        None,
    )
    if current_turn is None:
        raise RunRecordError(f"找不到当前轮：{current_turn_id}")
    if current_turn.report_markdown is None:
        raise RunRecordError("当前轮没有已校验报告，不能导出报告包")

    output_dir.mkdir(parents=True, exist_ok=True)
    targets = tuple(output_dir / name for name in EXPORT_FILENAMES)
    existing = [path.name for path in targets if path.exists()]
    if existing:
        raise RunRecordError(
            "导出不会覆盖已有文件：" + "、".join(existing)
        )

    record_text = (
        json.dumps(
            record.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    charts = [
        chart.model_dump(mode="json")
        for turn in record.turns
        for chart in turn.charts
    ]
    chart_text = (
        json.dumps(
            {
                "schema_version": "1.5.6-h3-chart-export-v1",
                "session_id": record.session_id,
                "charts": charts,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    facts_text = _facts_csv(record)
    report_text = current_turn.report_markdown
    for label, text in (
        ("run_record.json", record_text),
        ("business_report.md", report_text),
        ("facts.csv", facts_text),
        ("chart_data.json", chart_text),
    ):
        _ensure_safe_text(text, label)

    _write_new_text(targets[0], record_text)
    _write_new_text(targets[1], report_text)
    _write_new_text(targets[2], facts_text)
    _write_new_text(targets[3], chart_text)
    return targets
