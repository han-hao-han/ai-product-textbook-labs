from __future__ import annotations

import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from .generation_client import read_generation_state
from .io_utils import read_json, write_json_atomic, write_text_atomic


EXPERIENCE_TYPES = {
    "in_scope": "知识库内",
    "boundary": "边界",
    "out_of_scope": "知识库外",
}


def _saved_results(run_dir: Path) -> list[tuple[Path, dict[str, Any]]]:
    saved_dir = run_dir / "interactive" / "saved"
    if not saved_dir.is_dir():
        return []
    results: list[tuple[Path, dict[str, Any]]] = []
    for directory in sorted(saved_dir.glob("result_[0-9][0-9][0-9]")):
        path = directory / "result.json"
        if path.is_file():
            results.append((directory, read_json(path)))
    return results


def build_checkpoint3_report(run_dir: Path) -> tuple[Path, Path]:
    checkpoint_dir = run_dir / "checkpoints" / "checkpoint_3"
    if checkpoint_dir.exists():
        raise FileExistsError("检查点3报告已存在，拒绝覆盖")
    selected: dict[str, tuple[Path, dict[str, Any]]] = {}
    for directory, result in _saved_results(run_dir):
        kind = result.get("reader_experience_type")
        if kind in EXPERIENCE_TYPES and kind not in selected:
            selected[str(kind)] = (directory, result)
    missing = sorted(set(EXPERIENCE_TYPES) - set(selected))
    if missing:
        raise ValueError(
            "检查点3需要各保存一条知识库内、边界和知识库外结果；"
            f"缺少：{missing}"
        )
    generation_state = read_generation_state(run_dir)
    final_states = {
        kind: result["final_state"]
        for kind, (_, result) in selected.items()
    }
    acceptable = (
        final_states["in_scope"] == "answered"
        and final_states["boundary"]
        in {"retrieval_rejected", "model_refused"}
        and final_states["out_of_scope"]
        in {"retrieval_rejected", "model_refused"}
    )
    if acceptable and generation_state.get("status") == "passed":
        status = "passed"
    elif any(
        state in {"generation_failed", "validation_failed"}
        for state in final_states.values()
    ) or generation_state.get("status") == "blocked":
        status = "blocked"
    else:
        status = "warning"
    records = []
    for kind in ("in_scope", "boundary", "out_of_scope"):
        directory, result = selected[kind]
        records.append(
            {
                "reader_experience_type": kind,
                "label": EXPERIENCE_TYPES[kind],
                "saved_result": (
                    f"interactive/saved/{directory.name}/result.json"
                ),
                "question": result["question"],
                "final_state": result["final_state"],
                "top_k": result["top_k"],
                "total_elapsed_seconds": result["total_elapsed_seconds"],
            }
        )
    payload = {
        "schema_version": "checkpoint_3_report_v1",
        "checkpoint": "checkpoint_3",
        "title": "完整RAG问答",
        "experiment_run_id": run_dir.name,
        "created_at": datetime.now().astimezone().isoformat(),
        "status": status,
        "generation_client_state": generation_state,
        "reader_experience_records": records,
        "formal_evaluation_run": False,
        "codex_judge_called": False,
    }
    lines = [
        "# 检查点3报告：完整RAG问答",
        "",
        "## 状态",
        "",
        f"```text\n{status}\n```",
        "",
        "## 三类读者体验",
        "",
    ]
    for record in records:
        lines.extend(
            [
                f"### {record['label']}",
                "",
                f"- 问题：{record['question']}",
                f"- 最终状态：`{record['final_state']}`",
                f"- Top k：{record['top_k']}",
                f"- 总耗时：{record['total_elapsed_seconds']}秒",
                f"- 保存结果：`{record['saved_result']}`",
                "",
            ]
        )
    lines.extend(
        [
            "## 读者应该观察什么",
            "",
            "- Top 1门控拒答不会调用在线模型；",
            "- 门控通过后模型仍可因证据不足返回model_refused；",
            "- answered必须通过Schema、引用集合和Markdown安全校验；",
            "- 模型只看到重排后的证据，不看到分数、排名或阈值；",
            "",
            "## 真实性声明",
            "",
            "本报告只汇总用户显式保存的三类现场体验结果；"
            "未运行30道正式题，未调用Codex Judge。",
            "",
        ]
    )
    checkpoints_dir = run_dir / "checkpoints"
    checkpoints_dir.mkdir(parents=True, exist_ok=True)
    staging_dir = Path(
        tempfile.mkdtemp(prefix=".checkpoint_3.", dir=checkpoints_dir)
    )
    try:
        write_json_atomic(staging_dir / "report.json", payload)
        write_text_atomic(staging_dir / "report.md", "\n".join(lines))
        os.replace(staging_dir, checkpoint_dir)
        return (
            checkpoint_dir / "report.md",
            checkpoint_dir / "report.json",
        )
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise
