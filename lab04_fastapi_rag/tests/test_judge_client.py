from __future__ import annotations

import json

import pytest

from src.judge_client import (
    BlindJudgeInput,
    _build_codex_command,
    _parse_events,
    _resolve_codex_entrypoint,
    build_judge_prompt,
)
from src.judge_config import load_judge_config


def _input() -> BlindJudgeInput:
    return BlindJudgeInput(
        question_id="Q1",
        question="问题",
        required_points=("要点A",),
        optional_points=(),
        critical_errors=("错误A",),
        final_answer="答案",
        cited_chunks=(
            {
                "chunk_id": "c1",
                "source_path": "docs/a.md",
                "section_path": "章节",
                "content": "证据",
                "score": "不应出现",
            },
        ),
    )


def test_prompt_contains_only_blind_chunk_fields() -> None:
    prompt = build_judge_prompt(_input())
    assert "docs/a.md" in prompt
    assert "不应出现" not in prompt
    assert '"score"' not in prompt


def test_parse_events_accepts_agent_only_jsonl() -> None:
    stdout = "\n".join(
        [
            json.dumps({"type": "thread.started", "thread_id": "x"}),
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {"type": "agent_message", "text": "{}"},
                }
            ),
            json.dumps({"type": "turn.completed"}),
        ]
    )
    _, event_types, forbidden = _parse_events(stdout)
    assert event_types[-1] == "turn.completed"
    assert forbidden == []


@pytest.mark.parametrize(
    "item_type",
    ["command_execution", "file_change", "mcp_tool_call", "web_search"],
)
def test_parse_events_detects_tool_contamination(item_type: str) -> None:
    stdout = json.dumps(
        {
            "type": "item.completed",
            "item": {"type": item_type},
        }
    )
    _, _, forbidden = _parse_events(stdout)
    assert forbidden == [item_type]


def test_parse_events_rejects_non_json_line() -> None:
    with pytest.raises(ValueError, match="无法解析"):
        _parse_events("not json")


def test_resolve_codex_uses_cmd_wrapper() -> None:
    entrypoint = _resolve_codex_entrypoint()
    assert entrypoint.codex_cmd.lower().endswith("codex.cmd")
    assert entrypoint.command_interpreter.lower().endswith("cmd.exe")
    command = _build_codex_command(entrypoint, ["--version"])
    assert command[:4] == [
        entrypoint.command_interpreter,
        "/d",
        "/s",
        "/c",
    ]
    assert "codex.cmd" in command[4].lower()


def test_global_cli_arguments_precede_exec() -> None:
    config = load_judge_config()
    arguments = config.command_arguments
    assert config.cli_version == "0.145.0"
    assert config.probe_series == "h3_probe_codex_cli_0_145_0"
    exec_index = arguments.index("exec")
    assert arguments.index("--ask-for-approval") < exec_index
    assert arguments.index("--sandbox") < exec_index
    assert arguments.index("--ephemeral") > exec_index
    assert arguments.index("--json") > exec_index
    config_index = arguments.index("--config")
    assert arguments[config_index + 1] == "model_reasoning_effort=medium"
