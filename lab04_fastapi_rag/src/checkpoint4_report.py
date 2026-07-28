from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from .h2_questions import load_h2_question_set
from .io_utils import read_json, sha256_file, write_json_atomic, write_text_atomic
from .judge_config import load_judge_config
from .paths import (
    EVALUATION_QUESTIONS_PATH,
    JUDGE_CONFIG_PATH,
    JUDGE_FORMAL_DIR_NAME,
    JUDGE_INPUTS_DIR_NAME,
    JUDGE_OUTPUT_SCHEMA_PATH,
    JUDGE_PROMPT_PATH,
    RETRIEVAL_GATE_PATH,
)


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _question_records(run_dir: Path) -> list[dict[str, Any]]:
    question_set = load_h2_question_set(EVALUATION_QUESTIONS_PATH)
    records: list[dict[str, Any]] = []
    for question in question_set.questions:
        attempt = (
            run_dir
            / "evaluation"
            / "questions"
            / question.question_id
            / "attempt_001"
        )
        result = read_json(attempt / "result.json")
        comparison = read_json(attempt / "comparison.json")
        records.append(
            {
                "question": question,
                "result": result,
                "comparison": comparison,
            }
        )
    return records


def _retrieval_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    items = [
        item["comparison"]["retrieval"]
        for item in records
        if item["question"].scope == "in_scope"
    ]
    single = [item for item in items if item["single_source"]]
    top1_hits = sum(item["top1_reasonable_hit"] is True for item in single)
    top5_counts = Counter(item["top5_source_status"] for item in items)
    return {
        "top1_single_source_hits": top1_hits,
        "top1_single_source_denominator": len(single),
        "top1_reasonable_hit_rate": _rate(top1_hits, len(single)),
        "top5_full_hits": top5_counts["full"],
        "top5_partial_hits": top5_counts["partial"],
        "top5_misses": top5_counts["miss"],
        "top5_denominator": len(items),
        "top5_source_hit_rate": _rate(top5_counts["full"], len(items)),
        "partial_counts_as_failure_in_aggregate": True,
    }


def _classification_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    items = [
        item["comparison"]["classification"]
        for item in records
        if item["question"].scope == "in_scope"
    ]
    strict = sum(item["strict_correct"] is True for item in items)
    acceptable = sum(item["acceptable_correct"] is True for item in items)
    failures = sum(item["classification_failed"] is True for item in items)
    return {
        "strict_correct": strict,
        "acceptable_correct": acceptable,
        "denominator": len(items),
        "strict_accuracy": _rate(strict, len(items)),
        "acceptable_accuracy": _rate(acceptable, len(items)),
        "failure_count": failures,
        "acceptable_rule": (
            "effective_type_matches_frozen_label_including_comprehensive_fallback"
        ),
    }


def _refusal_metrics(
    records: list[dict[str, Any]],
    scope: str,
) -> dict[str, Any]:
    items = [
        item["comparison"]["refusal"]
        for item in records
        if item["question"].scope == scope
    ]
    correct = sum(item["refusal_correct"] is True for item in items)
    mechanism = sum(
        item["mechanism_conforming"] is True for item in items
    )
    return {
        "scope": scope,
        "correct_refusals": correct,
        "mechanism_conforming": mechanism,
        "denominator": len(items),
        "refusal_accuracy": _rate(correct, len(items)),
        "mechanism_conformity_rate": _rate(mechanism, len(items)),
        "expected_mechanism": (
            "model_refused" if scope == "boundary" else "retrieval_rejected"
        ),
    }


def _answer_metrics(
    records: list[dict[str, Any]],
    judge_summary: dict[str, Any],
) -> dict[str, Any]:
    in_scope_count = sum(
        item["question"].scope == "in_scope" for item in records
    )
    grades = Counter(
        str(item["answer_grade"])
        for item in judge_summary["records"]
        if item.get("answer_grade") is not None
    )
    judged = sum(grades.values())
    acceptable = grades["fully_correct"] + grades["mostly_correct"]
    return {
        "grade_distribution": {
            "fully_correct": grades["fully_correct"],
            "mostly_correct": grades["mostly_correct"],
            "incorrect": grades["incorrect"],
        },
        "judged_answer_count": judged,
        "formal_in_scope_denominator": in_scope_count,
        "not_judged_or_no_valid_answer_count": in_scope_count - judged,
        "fully_correct_rate": _rate(
            grades["fully_correct"],
            in_scope_count,
        ),
        "acceptable_answer_rate": _rate(acceptable, in_scope_count),
        "acceptable_grades": ["fully_correct", "mostly_correct"],
        "unjudged_counts_as_not_acceptable": True,
    }


def _render_report(report: dict[str, Any]) -> str:
    retrieval = report["metrics"]["retrieval"]
    classification = report["metrics"]["classification"]
    answers = report["metrics"]["answers"]
    boundary = report["metrics"]["boundary_refusal"]
    outside = report["metrics"]["out_of_scope_refusal"]
    lines = [
        "# 检查点4：校准、正式评价与Codex审核",
        "",
        f"- 状态：`{report['status']}`",
        f"- 实验运行：`{report['experiment_run_id']}`",
        f"- 正式题：{report['evaluation']['completed_count']}/30",
        f"- 正式题集SHA-256：`{report['evaluation']['question_set_sha256']}`",
        f"- 门控阈值：`{report['retrieval_gate']['threshold']!r}`",
        "- 正式运行后回调阈值：否",
        f"- 在线生成题数：{report['evaluation']['online_generation_question_count']}",
        f"- Codex Judge输入：{report['judge']['input_count']}",
        f"- Judge状态：{report['judge']['status_counts']}",
        "",
        "## 检索",
        "",
        (
            "- Top 1合理命中率："
            f"{retrieval['top1_reasonable_hit_rate']:.4f} "
            f"({retrieval['top1_single_source_hits']}/"
            f"{retrieval['top1_single_source_denominator']})"
        ),
        (
            "- 整体Top 5来源命中率："
            f"{retrieval['top5_source_hit_rate']:.4f} "
            f"({retrieval['top5_full_hits']}/{retrieval['top5_denominator']})"
        ),
        f"- Top 5部分命中：{retrieval['top5_partial_hits']}",
        f"- Top 5未命中：{retrieval['top5_misses']}",
        "",
        "## 分类",
        "",
        (
            f"- 严格准确率：{classification['strict_accuracy']:.4f} "
            f"({classification['strict_correct']}/"
            f"{classification['denominator']})"
        ),
        (
            f"- 可接受准确率：{classification['acceptable_accuracy']:.4f} "
            f"({classification['acceptable_correct']}/"
            f"{classification['denominator']})"
        ),
        f"- 分类失败：{classification['failure_count']}",
        "",
        "## 回答与拒答",
        "",
        f"- Judge等级分布：{answers['grade_distribution']}",
        (
            f"- 完全正确率：{answers['fully_correct_rate']:.4f}；"
            f"可接受回答率：{answers['acceptable_answer_rate']:.4f}"
        ),
        (
            "- 无有效答案或未成功审核："
            f"{answers['not_judged_or_no_valid_answer_count']}"
        ),
        (
            f"- 边界题拒答：{boundary['correct_refusals']}/"
            f"{boundary['denominator']}；机制符合："
            f"{boundary['mechanism_conforming']}/{boundary['denominator']}"
        ),
        (
            f"- 库外题拒答：{outside['correct_refusals']}/"
            f"{outside['denominator']}；机制符合："
            f"{outside['mechanism_conforming']}/{outside['denominator']}"
        ),
        "",
        "## 评价边界",
        "",
        "- 检索、分类和拒答机制由程序计算。",
        "- 回答语义等级只来自独立Codex Judge attempt_001。",
        "- 生成模型没有评价自己的答案。",
        "- API Key、Authorization Header和未引用Top 5未发送给Judge。",
        "- 完整运行记录仅保存在本地，不作为仓库公开示例自动导出。",
        "",
        "## 下一步",
        "",
        "请人工查看逐题comparison、Judge首次输出和失败状态，"
        "确认后再进入H4 Streamlit现场体验与最终工程验收。",
        "",
    ]
    return "\n".join(lines)


def build_checkpoint4_report(run_dir: Path) -> tuple[Path, Path]:
    evaluation_summary = read_json(run_dir / "evaluation" / "summary.json")
    inputs_manifest = read_json(
        run_dir / "judge" / JUDGE_INPUTS_DIR_NAME / "manifest.json"
    )
    judge_summary = read_json(
        run_dir / "judge" / JUDGE_FORMAL_DIR_NAME / "summary.json"
    )
    if evaluation_summary.get("completed_count") != 30:
        raise ValueError("正式30题尚未全部完成")
    if judge_summary.get("completed_count") != inputs_manifest.get(
        "input_count"
    ):
        raise ValueError("Judge首次审核尚未全部形成终态")
    records = _question_records(run_dir)
    judge_config = load_judge_config(require_frozen=True)
    gate = read_json(RETRIEVAL_GATE_PATH)

    runtime_warning = evaluation_summary.get("status") == "warning"
    judge_warning = judge_summary.get("status") == "warning"
    report = {
        "schema_version": "checkpoint_4_report_v1",
        "experiment_run_id": run_dir.name,
        "created_at": datetime.now().astimezone().isoformat(),
        "status": "warning" if runtime_warning or judge_warning else "passed",
        "evaluation": {
            "question_count": 30,
            "completed_count": evaluation_summary["completed_count"],
            "question_set_sha256": evaluation_summary[
                "question_set_sha256"
            ],
            "formal_metrics_attempt": "attempt_001",
            "final_states": evaluation_summary["final_states"],
            "online_generation_question_count": evaluation_summary[
                "online_generation_question_count"
            ],
        },
        "retrieval_gate": {
            "threshold": gate["threshold"],
            "retune_after_evaluation": False,
            "config_sha256": sha256_file(RETRIEVAL_GATE_PATH),
        },
        "judge": {
            "provider": "codex_cli_chatgpt",
            "model": judge_config.model,
            "reasoning_effort": judge_config.reasoning_effort,
            "cli_version": judge_config.cli_version,
            "input_count": inputs_manifest["input_count"],
            "status_counts": judge_summary["status_counts"],
            "config_sha256": sha256_file(JUDGE_CONFIG_PATH),
            "output_schema_sha256": sha256_file(
                JUDGE_OUTPUT_SCHEMA_PATH
            ),
            "prompt_sha256": sha256_file(JUDGE_PROMPT_PATH),
            "formal_metrics_attempt": "attempt_001",
            "api_key_saved": False,
        },
        "metrics": {
            "retrieval": _retrieval_metrics(records),
            "classification": _classification_metrics(records),
            "answers": _answer_metrics(records, judge_summary),
            "boundary_refusal": _refusal_metrics(records, "boundary"),
            "out_of_scope_refusal": _refusal_metrics(
                records,
                "out_of_scope",
            ),
        },
        "program_grades_answer_semantics": False,
        "generation_model_grades_itself": False,
    }
    output_dir = run_dir / "checkpoints" / "checkpoint_4"
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "report.json"
    markdown_path = output_dir / "report.md"
    write_json_atomic(json_path, report)
    write_text_atomic(markdown_path, _render_report(report))
    return markdown_path, json_path
