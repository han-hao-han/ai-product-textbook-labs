from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .io_utils import read_json, sha256_file
from .paths import JUDGE_CONFIG_PATH, JUDGE_OUTPUT_SCHEMA_PATH, JUDGE_PROMPT_PATH


ALLOWED_STATUSES = {
    "h3_judge_candidate_user_confirmed",
    "h3_judge_frozen_real_probe_passed",
}


@dataclass(frozen=True)
class JudgeConfig:
    path: Path
    status: str
    cli_version: str
    model: str
    reasoning_effort: str
    probe_series: str
    timeout_seconds: int
    output_schema_path: Path
    command_arguments: tuple[str, ...]

    @property
    def sha256(self) -> str:
        return sha256_file(self.path)


def _require_exact(payload: dict[str, Any], path: str, expected: Any) -> None:
    current: Any = payload
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            raise ValueError(f"Judge配置缺少字段：{path}")
        current = current[part]
    if current != expected:
        raise ValueError(
            f"Judge配置偏离H3确认方案：{path} expected={expected!r}, "
            f"actual={current!r}"
        )


def load_judge_config(
    path: Path = JUDGE_CONFIG_PATH,
    *,
    require_frozen: bool = False,
) -> JudgeConfig:
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise ValueError("Judge配置必须是JSON对象")
    if payload.get("schema_version") != "judge_config_v1":
        raise ValueError("不支持的Judge配置版本")
    status = str(payload.get("status", ""))
    if status not in ALLOWED_STATUSES:
        raise ValueError("Judge配置尚未经过H3确认")
    if require_frozen and status != "h3_judge_frozen_real_probe_passed":
        raise ValueError("Judge配置尚未通过本机真实探针，禁止正式盲审")

    exact_values = {
        "provider": "codex_cli_chatgpt",
        "cli_version": "0.145.0",
        "model": "gpt-5.6-sol",
        "reasoning_effort": "medium",
        "execution.entrypoint": "codex.cmd_via_cmd.exe",
        "execution.probe_series": "h3_probe_codex_cli_0_145_0",
        "execution.one_question_per_process": True,
        "execution.serial": True,
        "execution.working_directory": "project_root",
        "execution.sandbox": "read-only",
        "execution.approval_policy": "never",
        "execution.ephemeral": True,
        "execution.ignore_user_config": True,
        "execution.ignore_execpolicy_rules": True,
        "execution.jsonl_events": True,
        "execution.timeout_seconds": 300,
        "execution.automatic_retries": 0,
        "structured_output.mode": "codex_output_schema",
        "structured_output.schema_path": "configs/judge_output.schema.json",
        "contamination_policy.prompt_forbids_tools": True,
        "contamination_policy.any_tool_or_command_event_is_contaminated": True,
        "contamination_policy.unparseable_jsonl_is_contaminated": True,
        "formal_metrics_attempt": "attempt_001",
    }
    for field, expected in exact_values.items():
        _require_exact(payload, field, expected)

    if require_frozen:
        frozen_probe_values = {
            "h3_verification.probe_series": "h3_probe_codex_cli_0_145_0",
            "h3_verification.probe_attempt": "attempt_002",
            "h3_verification.status": "judged",
            "h3_verification.cli_version": "0.145.0",
            "h3_verification.model": "gpt-5.6-sol",
            "h3_verification.reasoning_effort": "medium",
            "h3_verification.forbidden_events": [],
            "h3_verification.output_schema_sha256": (
                "ee30e32ab6fff55cc725e8cae310bb8c7423c08db12bebe6f39ec0b35973f5c8"
            ),
            "h3_verification.prompt_sha256": (
                "ad23881d72c2d37565d1a82db9d20c3f401451f3b5bece907145ab8b5c1f1336"
            ),
        }
        for field, expected in frozen_probe_values.items():
            _require_exact(payload, field, expected)

    output_schema_path = path.parent.parent / str(
        payload["structured_output"]["schema_path"]
    )
    if output_schema_path.resolve() != JUDGE_OUTPUT_SCHEMA_PATH.resolve():
        raise ValueError("Judge输出Schema路径偏离冻结位置")
    if not output_schema_path.is_file():
        raise FileNotFoundError("缺少Judge输出Schema")
    if require_frozen:
        if sha256_file(output_schema_path) != payload["h3_verification"][
            "output_schema_sha256"
        ]:
            raise ValueError("Judge输出Schema已偏离H3真实探针冻结哈希")
        if sha256_file(JUDGE_PROMPT_PATH) != payload["h3_verification"]["prompt_sha256"]:
            raise ValueError("Judge Prompt已偏离H3真实探针冻结哈希")

    command_arguments = (
        "--model",
        "gpt-5.6-sol",
        "--config",
        "model_reasoning_effort=medium",
        "--sandbox",
        "read-only",
        "--ask-for-approval",
        "never",
        "exec",
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--json",
        "--color",
        "never",
    )
    return JudgeConfig(
        path=path,
        status=status,
        cli_version="0.145.0",
        model="gpt-5.6-sol",
        reasoning_effort="medium",
        probe_series="h3_probe_codex_cli_0_145_0",
        timeout_seconds=300,
        output_schema_path=output_schema_path,
        command_arguments=command_arguments,
    )
