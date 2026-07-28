from __future__ import annotations

import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from .io_utils import sha256_file, write_json_atomic, write_text_atomic
from .paths import (
    ANSWER_PROMPT_PATH,
    CLASSIFICATION_PROMPT_PATH,
    GENERATION_CONFIG_PATH,
    RETRIEVAL_GATE_PATH,
)


def _next_result_name(directory: Path) -> str:
    existing = sorted(
        path.name
        for path in directory.glob("result_[0-9][0-9][0-9]")
        if path.is_dir()
    )
    number = int(existing[-1].split("_")[-1]) + 1 if existing else 1
    return f"result_{number:03d}"


def _result_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# RAG问答保存结果",
        "",
        f"- 状态：`{result['final_state']}`",
        f"- 问题：{result['question']}",
        f"- Top k：{result['top_k']}",
        f"- 总耗时：{result['total_elapsed_seconds']}秒",
        "",
    ]
    answer = result.get("answer")
    if isinstance(answer, dict):
        if answer.get("answerable"):
            lines.extend(["## 回答", "", str(answer["answer"]), ""])
        else:
            lines.extend(
                ["## 拒答", "", str(answer.get("refusal_reason")), ""]
            )
    if result.get("citations"):
        lines.extend(["## 参考依据", ""])
        for citation in result["citations"]:
            lines.extend(
                [
                    f"### {citation['page_title']}",
                    "",
                    f"- Chunk：`{citation['chunk_id']}`",
                    f"- 来源：{citation['source_url']}",
                    "",
                    citation["excerpt"],
                    "",
                ]
            )
    return "\n".join(lines)


def save_interactive_result(
    run_dir: Path,
    result: dict[str, Any],
    *,
    confirmed: bool,
) -> Path:
    if not confirmed:
        raise ValueError("保存前必须由用户显式确认")
    saved_dir = run_dir / "interactive" / "saved"
    saved_dir.mkdir(parents=True, exist_ok=True)
    result_name = _next_result_name(saved_dir)
    target_dir = saved_dir / result_name
    staging_dir = Path(
        tempfile.mkdtemp(prefix=f".{result_name}.", dir=saved_dir)
    )
    public_result = {
        key: value
        for key, value in result.items()
        if key not in {"retrieval", "generation"}
    }
    generation = result.get("generation") or {}
    retrieval = result.get("retrieval") or {}
    try:
        write_json_atomic(staging_dir / "result.json", public_result)
        write_text_atomic(
            staging_dir / "result.md",
            _result_markdown(result),
        )
        write_json_atomic(
            staging_dir / "retrieval_results.json",
            retrieval,
        )
        write_json_atomic(
            staging_dir / "generation_context.json",
            {
                "schema_version": "saved_generation_context_v1",
                "online_model_called": generation.get(
                    "online_model_called",
                    False,
                ),
                "evidence_sent": generation.get("evidence_sent", []),
                "raw_responses": generation.get("raw_responses", []),
                "error": generation.get("error"),
                "api_key_saved": False,
                "complete_prompt_saved": False,
            },
        )
        write_json_atomic(
            staging_dir / "snapshot_metadata.json",
            {
                "schema_version": "interactive_snapshot_metadata_v1",
                "saved_at": datetime.now().astimezone().isoformat(),
                "experiment_run_id": run_dir.name,
                "generation_config_sha256": sha256_file(
                    GENERATION_CONFIG_PATH
                ),
                "retrieval_gate_sha256": sha256_file(
                    RETRIEVAL_GATE_PATH
                ),
                "classification_prompt_sha256": sha256_file(
                    CLASSIFICATION_PROMPT_PATH
                ),
                "answer_prompt_sha256": sha256_file(ANSWER_PROMPT_PATH),
                "api_key_saved": False,
                "local_absolute_path_saved": False,
            },
        )
        os.replace(staging_dir, target_dir)
        return target_dir
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise
