from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .io_utils import (
    sha256_text,
    write_json_atomic,
    write_text_atomic,
)
from .judge_config import JudgeConfig
from .judge_schemas import parse_judge_output
from .paths import JUDGE_PROMPT_PATH, PROJECT_ROOT


FORBIDDEN_ITEM_TYPES = {
    "command_execution",
    "computer_use",
    "file_change",
    "mcp_tool_call",
    "tool_call",
    "web_search",
}
SECRET_PATTERNS = (
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{10,}\b"),
)


@dataclass(frozen=True)
class BlindJudgeInput:
    question_id: str
    question: str
    required_points: tuple[str, ...]
    optional_points: tuple[str, ...]
    critical_errors: tuple[str, ...]
    final_answer: str
    cited_chunks: tuple[dict[str, str], ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "question_id": self.question_id,
            "question": self.question,
            "required_points": list(self.required_points),
            "optional_points": list(self.optional_points),
            "critical_errors": list(self.critical_errors),
            "final_answer": self.final_answer,
            "cited_chunks": list(self.cited_chunks),
        }


@dataclass(frozen=True)
class CodexEntrypoint:
    command_interpreter: str
    codex_cmd: str


def build_judge_prompt(
    item: BlindJudgeInput,
    prompt_path: Path = JUDGE_PROMPT_PATH,
) -> str:
    template = prompt_path.read_text(encoding="utf-8")
    chunks = [
        {
            "chunk_id": chunk["chunk_id"],
            "source_path": chunk["source_path"],
            "section_path": chunk["section_path"],
            "content": chunk["content"],
        }
        for chunk in item.cited_chunks
    ]
    return template.format(
        question=item.question,
        required_points=json.dumps(
            item.required_points,
            ensure_ascii=False,
            indent=2,
        ),
        optional_points=json.dumps(
            item.optional_points,
            ensure_ascii=False,
            indent=2,
        ),
        critical_errors=json.dumps(
            item.critical_errors,
            ensure_ascii=False,
            indent=2,
        ),
        final_answer=item.final_answer,
        cited_chunks=json.dumps(chunks, ensure_ascii=False, indent=2),
    )


def _sanitize(text: str) -> str:
    sanitized = text
    replacements = {
        str(PROJECT_ROOT.resolve()): "<PROJECT_ROOT>",
        str(Path.home().resolve()): "<USER_HOME>",
    }
    codex_home = os.environ.get("CODEX_HOME", "").strip()
    if codex_home:
        replacements[str(Path(codex_home).resolve())] = "<CODEX_HOME>"
    for raw, replacement in sorted(
        replacements.items(),
        key=lambda pair: len(pair[0]),
        reverse=True,
    ):
        sanitized = sanitized.replace(raw, replacement)
        sanitized = sanitized.replace(raw.replace("\\", "\\\\"), replacement)
    for pattern in SECRET_PATTERNS:
        sanitized = pattern.sub("<REDACTED_CREDENTIAL>", sanitized)
    return sanitized


def _parse_events(stdout: str) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    events: list[dict[str, Any]] = []
    event_types: list[str] = []
    forbidden: list[str] = []
    for line_number, line in enumerate(stdout.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(
                f"Codex JSONL第{line_number}行无法解析"
            ) from error
        if not isinstance(event, dict):
            raise ValueError(f"Codex JSONL第{line_number}行不是对象")
        events.append(event)
        event_type = str(event.get("type", "unknown"))
        event_types.append(event_type)
        item = event.get("item")
        if isinstance(item, dict):
            item_type = str(item.get("type", ""))
            if item_type in FORBIDDEN_ITEM_TYPES:
                forbidden.append(item_type)
        if event_type in FORBIDDEN_ITEM_TYPES:
            forbidden.append(event_type)
    return events, event_types, sorted(set(forbidden))


def _resolve_codex_entrypoint(
    environment: dict[str, str] | None = None,
) -> CodexEntrypoint:
    if os.name != "nt":
        raise RuntimeError("当前冻结Judge入口仅支持Windows codex.cmd")
    env = os.environ if environment is None else environment
    interpreter = env.get("COMSPEC", "").strip() or shutil.which("cmd.exe")
    if not interpreter:
        raise FileNotFoundError("未找到Windows命令解释器cmd.exe")

    candidates: list[Path] = []
    resolved_by_path = shutil.which("codex.cmd", path=env.get("PATH"))
    if resolved_by_path:
        candidates.append(Path(resolved_by_path))
    appdata = env.get("APPDATA", "").strip()
    if appdata:
        candidates.append(Path(appdata) / "npm" / "codex.cmd")
    codex_home = env.get("CODEX_HOME", "").strip()
    if codex_home:
        candidates.append(
            Path(codex_home).parent / "AppData" / "Roaming" / "npm" / "codex.cmd"
        )
    for candidate in candidates:
        if candidate.is_file():
            return CodexEntrypoint(
                command_interpreter=str(Path(interpreter).resolve()),
                codex_cmd=str(candidate.resolve()),
            )
    raise FileNotFoundError("未找到npm安装的codex.cmd包装入口")


def _build_codex_command(
    entrypoint: CodexEntrypoint,
    arguments: list[str],
) -> list[str]:
    command_line = subprocess.list2cmdline(
        [entrypoint.codex_cmd, *arguments]
    )
    return [
        entrypoint.command_interpreter,
        "/d",
        "/s",
        "/c",
        command_line,
    ]


def _codex_version(
    entrypoint: CodexEntrypoint,
    env: dict[str, str],
) -> str:
    completed = subprocess.run(
        _build_codex_command(entrypoint, ["--version"]),
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    if completed.returncode != 0:
        raise RuntimeError("无法读取Codex CLI版本")
    version = completed.stdout.strip()
    if not version.startswith("codex-cli "):
        raise RuntimeError("Codex CLI版本输出格式异常")
    return version.removeprefix("codex-cli ").strip()


def run_judge_attempt(
    item: BlindJudgeInput,
    *,
    attempt_dir: Path,
    config: JudgeConfig,
    environment: dict[str, str] | None = None,
    formal_evaluation: bool = False,
) -> dict[str, Any]:
    if attempt_dir.exists():
        raise FileExistsError(f"Judge attempt已存在，拒绝覆盖：{attempt_dir}")
    attempt_dir.mkdir(parents=True)
    env = dict(os.environ if environment is None else environment)
    entrypoint = _resolve_codex_entrypoint(env)
    cli_version = _codex_version(entrypoint, env)
    if cli_version != config.cli_version:
        raise RuntimeError(
            f"Codex CLI版本偏离冻结值：expected={config.cli_version}, "
            f"actual={cli_version}"
        )

    prompt = build_judge_prompt(item)
    output_path = attempt_dir / "last_message.json"
    codex_arguments = [
        *config.command_arguments,
        "--output-schema",
        str(config.output_schema_path.resolve()),
        "--output-last-message",
        str(output_path.resolve()),
        "--cd",
        str(PROJECT_ROOT.resolve()),
        "-",
    ]
    command = _build_codex_command(entrypoint, codex_arguments)
    write_json_atomic(attempt_dir / "blind_input.json", item.to_payload())
    started = time.perf_counter()
    timed_out = False
    try:
        completed = subprocess.run(
            command,
            input=prompt,
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=config.timeout_seconds,
        )
        return_code: int | None = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except subprocess.TimeoutExpired as error:
        timed_out = True
        return_code = None
        stdout = str(error.stdout or "")
        stderr = str(error.stderr or "")
    elapsed = time.perf_counter() - started

    sanitized_stdout = _sanitize(stdout)
    sanitized_stderr = _sanitize(stderr)
    write_text_atomic(attempt_dir / "stdout.jsonl", sanitized_stdout)
    write_text_atomic(attempt_dir / "stderr.log", sanitized_stderr)
    status = "judge_failed"
    validation_error: str | None = None
    event_types: list[str] = []
    forbidden_events: list[str] = []
    parsed_output: dict[str, Any] | None = None
    event_parse_error: str | None = None
    if stdout.strip():
        try:
            _, event_types, forbidden_events = _parse_events(stdout)
        except ValueError as error:
            event_parse_error = str(error)

    if event_parse_error is not None:
        status = "judge_contaminated"
        validation_error = event_parse_error
    elif forbidden_events:
        status = "judge_contaminated"
        validation_error = (
            "Codex Judge使用了禁止的工具事件："
            + ", ".join(forbidden_events)
        )
    elif timed_out:
        validation_error = "Codex Judge超过冻结超时时间"
    elif return_code != 0:
        validation_error = f"Codex CLI非零退出：return_code={return_code}"
    elif not output_path.is_file():
        validation_error = "Codex未生成last_message"
    else:
        try:
            output_text = output_path.read_text(encoding="utf-8")
            result = parse_judge_output(
                output_text,
                required_points=item.required_points,
                allowed_critical_errors=item.critical_errors,
            )
        except (OSError, ValueError) as error:
            status = "judge_validation_failed"
            validation_error = f"{type(error).__name__}: {error}"
        else:
            status = "judged"
            parsed_output = result.model_dump(mode="json")
            write_json_atomic(
                attempt_dir / "parsed_output.json",
                parsed_output,
            )
    metadata = {
        "schema_version": "judge_attempt_v1",
        "question_id": item.question_id,
        "status": status,
        "attempt": attempt_dir.name,
        "model": config.model,
        "reasoning_effort": config.reasoning_effort,
        "cli_version": cli_version,
        "entrypoint": "codex.cmd_via_cmd.exe",
        "sandbox": "read-only",
        "working_directory": "project_root",
        "ephemeral": True,
        "automatic_retries": 0,
        "timed_out": timed_out,
        "return_code": return_code,
        "elapsed_seconds": round(elapsed, 6),
        "input_sha256": sha256_text(
            json.dumps(item.to_payload(), ensure_ascii=False, sort_keys=True)
        ),
        "prompt_sha256": sha256_text(prompt),
        "event_types": event_types,
        "forbidden_events": forbidden_events,
        "validation_error": validation_error,
        "credential_saved": False,
        "formal_evaluation": formal_evaluation,
    }
    write_json_atomic(attempt_dir / "metadata.json", metadata)
    return {
        **metadata,
        "output": parsed_output,
    }
