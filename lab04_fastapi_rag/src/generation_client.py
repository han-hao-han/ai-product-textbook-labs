from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Protocol, Sequence

from .generation_config import (
    GenerationConfig,
    installed_generation_dependency_versions,
)
from .generation_schemas import (
    QuestionClassification,
    RagAnswer,
    parse_classification,
    parse_rag_answer,
)
from .io_utils import (
    read_json,
    sha256_file,
    write_json_atomic,
)
from .paths import (
    ANSWER_PROMPT_PATH,
    CLASSIFICATION_PROMPT_PATH,
    GENERATION_CONFIG_PATH,
    RETRIEVAL_GATE_PATH,
)
from .prompt_builder import (
    build_answer_messages,
    build_classification_messages,
)
from .project_environment import load_project_environment


class GenerationCallError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        fatal: bool,
        temporary: bool,
        status_code: int | None,
        attempts: int,
    ) -> None:
        super().__init__(message)
        self.fatal = fatal
        self.temporary = temporary
        self.status_code = status_code
        self.attempts = attempts


class StructuredResponseError(ValueError):
    """The provider returned content that does not satisfy the frozen schema."""

    def __init__(
        self,
        message: str,
        *,
        record: CompletionRecord | None = None,
    ) -> None:
        super().__init__(message)
        self.record = record


@dataclass(frozen=True)
class CompletionRecord:
    purpose: str
    content: str
    response_id: str | None
    response_model: str | None
    finish_reason: str | None
    usage: dict[str, Any] | None
    attempts: int
    elapsed_seconds: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "purpose": self.purpose,
            "content": self.content,
            "response_id": self.response_id,
            "response_model": self.response_model,
            "finish_reason": self.finish_reason,
            "usage": self.usage,
            "attempts": self.attempts,
            "elapsed_seconds": self.elapsed_seconds,
        }


class GenerationBackend(Protocol):
    def classify(
        self,
        question: str,
    ) -> tuple[QuestionClassification, CompletionRecord]: ...

    def answer(
        self,
        question: str,
        question_type: str,
        hits: Sequence[dict[str, Any]],
    ) -> tuple[RagAnswer, CompletionRecord, list[dict[str, Any]]]: ...


def _usage_dict(usage: Any) -> dict[str, Any] | None:
    if usage is None:
        return None
    if hasattr(usage, "model_dump"):
        value = usage.model_dump()
        return value if isinstance(value, dict) else None
    return None


def _classify_api_error(error: Exception) -> tuple[bool, bool, int | None]:
    try:
        import openai
    except ImportError:
        return False, False, None
    status_code = getattr(error, "status_code", None)
    fatal = isinstance(
        error,
        (
            openai.AuthenticationError,
            openai.PermissionDeniedError,
        ),
    ) or status_code in {401, 403}
    temporary = isinstance(
        error,
        (
            openai.APIConnectionError,
            openai.APITimeoutError,
            openai.RateLimitError,
        ),
    ) or status_code in {429, 500, 502, 503, 504}
    if isinstance(error, openai.BadRequestError):
        fatal = True
    return fatal, temporary, status_code


class AliyunGenerationClient:
    def __init__(
        self,
        config: GenerationConfig,
        api_key: str,
        *,
        client_factory: Callable[..., Any] | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_key:
            raise ValueError("API Key不能为空")
        if client_factory is None:
            from openai import OpenAI

            client_factory = OpenAI
        self.config = config
        self.sleeper = sleeper
        self.client = client_factory(
            api_key=api_key,
            base_url=config.base_url,
            timeout=config.timeout_seconds,
            max_retries=0,
        )

    def _json_completion(
        self,
        purpose: str,
        messages: list[dict[str, str]],
    ) -> CompletionRecord:
        started = time.perf_counter()
        max_attempts = 1 + self.config.temporary_error_max_retries
        for attempt in range(1, max_attempts + 1):
            try:
                response = self.client.chat.completions.create(
                    model=self.config.model,
                    messages=messages,
                    response_format=self.config.response_format,
                    temperature=self.config.temperature,
                    stream=self.config.stream,
                    extra_body={
                        "enable_thinking": self.config.enable_thinking,
                    },
                )
                choice = response.choices[0]
                content = choice.message.content
                if not isinstance(content, str) or not content.strip():
                    raise StructuredResponseError("模型返回的JSON内容为空")
                return CompletionRecord(
                    purpose=purpose,
                    content=content,
                    response_id=getattr(response, "id", None),
                    response_model=getattr(response, "model", None),
                    finish_reason=getattr(choice, "finish_reason", None),
                    usage=_usage_dict(getattr(response, "usage", None)),
                    attempts=attempt,
                    elapsed_seconds=round(
                        time.perf_counter() - started,
                        6,
                    ),
                )
            except StructuredResponseError:
                raise
            except Exception as error:
                fatal, temporary, status_code = _classify_api_error(error)
                if temporary and attempt < max_attempts:
                    self.sleeper(self.config.retry_wait_seconds)
                    continue
                raise GenerationCallError(
                    f"{type(error).__name__}: {error}",
                    fatal=fatal,
                    temporary=temporary,
                    status_code=status_code,
                    attempts=attempt,
                ) from error
        raise AssertionError("unreachable")

    def classify(
        self,
        question: str,
    ) -> tuple[QuestionClassification, CompletionRecord]:
        record = self._json_completion(
            "classification",
            build_classification_messages(question),
        )
        try:
            parsed = parse_classification(record.content)
        except (ValueError, TypeError) as error:
            raise StructuredResponseError(
                f"分类响应未通过Schema：{error}",
                record=record,
            ) from error
        return parsed, record

    def answer(
        self,
        question: str,
        question_type: str,
        hits: Sequence[dict[str, Any]],
    ) -> tuple[RagAnswer, CompletionRecord, list[dict[str, Any]]]:
        messages, evidence = build_answer_messages(
            question,
            question_type,
            hits,
        )
        record = self._json_completion("answer", messages)
        try:
            parsed = parse_rag_answer(record.content)
        except (ValueError, TypeError) as error:
            raise StructuredResponseError(
                f"回答响应未通过Schema：{error}",
                record=record,
            ) from error
        return parsed, record, evidence


def read_generation_state(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "generation" / "current_state.json"
    if not path.is_file():
        return {
            "schema_version": "generation_current_state_v1",
            "status": "not_run",
            "latest_attempt": None,
        }
    payload = read_json(path)
    if payload.get("status") not in {
        "not_run",
        "retrieval_only",
        "passed",
        "blocked",
    }:
        raise ValueError("generation/current_state.json状态无效")
    return payload


def _next_attempt_name(attempts_dir: Path) -> str:
    existing = sorted(
        path.name
        for path in attempts_dir.glob("attempt_[0-9][0-9][0-9]")
        if path.is_dir()
    )
    number = int(existing[-1].split("_")[-1]) + 1 if existing else 1
    return f"attempt_{number:03d}"


def _sanitize_error(error: Exception) -> str:
    message = str(error)
    message = message.replace(str(Path.home()), "<USER_HOME>")
    return message[:4000]


def _snapshot_generation_config(run_dir: Path) -> None:
    directory = run_dir / "config_snapshot"
    directory.mkdir(parents=True, exist_ok=True)
    for source in (GENERATION_CONFIG_PATH, RETRIEVAL_GATE_PATH):
        target = directory / source.name
        if target.is_file():
            if sha256_file(target) != sha256_file(source):
                raise ValueError(f"运行配置快照与当前文件不一致：{source.name}")
        else:
            shutil.copyfile(source, target)


def prepare_generation_client(
    run_dir: Path,
    config: GenerationConfig,
    *,
    environment: dict[str, str] | None = None,
    backend_factory: Callable[[GenerationConfig, str], GenerationBackend]
    | None = None,
) -> dict[str, Any]:
    dependencies = installed_generation_dependency_versions(config)
    _snapshot_generation_config(run_dir)
    generation_dir = run_dir / "generation"
    attempts_dir = generation_dir / "attempts"
    attempts_dir.mkdir(parents=True, exist_ok=True)
    attempt_name = _next_attempt_name(attempts_dir)
    attempt_dir = attempts_dir / attempt_name
    staging_dir = Path(
        tempfile.mkdtemp(prefix=f".{attempt_name}.", dir=attempts_dir)
    )
    credential_environment = None
    if environment is None:
        credential_environment = load_project_environment(
            variable_name=config.api_key_environment_variable,
        )
        env = os.environ
    else:
        env = environment
    api_key = str(env.get(config.api_key_environment_variable, "")).strip()
    credential_source = (
        credential_environment.credential_source
        if credential_environment is not None
        else ("injected_environment" if api_key else "missing")
    )
    called_online = False
    probe: dict[str, Any] | None = None
    error_payload: dict[str, Any] | None = None
    status = "retrieval_only"
    reason = "missing_api_key"
    try:
        if api_key:
            called_online = True
            backend = (
                AliyunGenerationClient(config, api_key)
                if backend_factory is None
                else backend_factory(config, api_key)
            )
            classification, classification_record = backend.classify(
                "如何在FastAPI中声明请求体？"
            )
            answer, answer_record, _ = backend.answer(
                "根据证据，资源不存在时应如何返回404？",
                "concise_concept",
                [
                    {
                        "chunk_id": "probe_chunk_001",
                        "page_title": "能力测试证据",
                        "section_path": ["HTTPException"],
                        "source_path": "probe/only",
                        "chunk_index": 0,
                        "content": (
                            "资源不存在时，raise HTTPException("
                            "status_code=404, detail=\"Item not found\")。"
                        ),
                    }
                ],
            )
            status = "passed"
            reason = "json_mode_and_schemas_passed"
            probe = {
                "classification": {
                    "parsed": classification.model_dump(mode="json"),
                    "raw_response": classification_record.as_dict(),
                },
                "answer": {
                    "parsed": answer.model_dump(mode="json"),
                    "raw_response": answer_record.as_dict(),
                },
            }
        result = {
            "schema_version": "generation_preparation_v1",
            "experiment_run_id": run_dir.name,
            "attempt": attempt_name,
            "created_at": datetime.now().astimezone().isoformat(),
            "status": status,
            "reason": reason,
            "provider": config.provider,
            "region": config.region,
            "base_url": config.base_url,
            "model": config.model,
            "structured_output": config.response_format,
            "stream": config.stream,
            "temperature": config.temperature,
            "enable_thinking": config.enable_thinking,
            "output_token_cap_sent": False,
            "online_model_called": called_online,
            "api_key_present": bool(api_key),
            "api_key_saved": False,
            "credential_source": credential_source,
            "project_dotenv_checked": environment is None,
            "project_dotenv_exists": (
                credential_environment.dotenv_exists
                if credential_environment is not None
                else None
            ),
            "dependencies": dependencies,
            "generation_config_sha256": sha256_file(GENERATION_CONFIG_PATH),
            "retrieval_gate_sha256": sha256_file(RETRIEVAL_GATE_PATH),
            "classification_prompt_sha256": sha256_file(
                CLASSIFICATION_PROMPT_PATH
            ),
            "answer_prompt_sha256": sha256_file(ANSWER_PROMPT_PATH),
            "probe": probe,
            "error": error_payload,
        }
    except (GenerationCallError, StructuredResponseError) as error:
        status = (
            "blocked"
            if isinstance(error, StructuredResponseError)
            or getattr(error, "fatal", False)
            else "retrieval_only"
        )
        reason = (
            "structured_output_or_fatal_error"
            if status == "blocked"
            else "temporary_generation_error"
        )
        error_payload = {
            "error_type": type(error).__name__,
            "error_message": _sanitize_error(error),
            "status_code": getattr(error, "status_code", None),
            "temporary": getattr(error, "temporary", False),
            "fatal": status == "blocked",
            "attempts": getattr(error, "attempts", 1),
        }
        result = {
            "schema_version": "generation_preparation_v1",
            "experiment_run_id": run_dir.name,
            "attempt": attempt_name,
            "created_at": datetime.now().astimezone().isoformat(),
            "status": status,
            "reason": reason,
            "provider": config.provider,
            "region": config.region,
            "base_url": config.base_url,
            "model": config.model,
            "structured_output": config.response_format,
            "stream": config.stream,
            "temperature": config.temperature,
            "enable_thinking": config.enable_thinking,
            "output_token_cap_sent": False,
            "online_model_called": called_online,
            "api_key_present": bool(api_key),
            "api_key_saved": False,
            "credential_source": credential_source,
            "project_dotenv_checked": environment is None,
            "project_dotenv_exists": (
                credential_environment.dotenv_exists
                if credential_environment is not None
                else None
            ),
            "dependencies": dependencies,
            "generation_config_sha256": sha256_file(GENERATION_CONFIG_PATH),
            "retrieval_gate_sha256": sha256_file(RETRIEVAL_GATE_PATH),
            "classification_prompt_sha256": sha256_file(
                CLASSIFICATION_PROMPT_PATH
            ),
            "answer_prompt_sha256": sha256_file(ANSWER_PROMPT_PATH),
            "probe": probe,
            "error": error_payload,
        }
    try:
        write_json_atomic(staging_dir / "preparation.json", result)
        if probe is not None:
            write_json_atomic(staging_dir / "probe.json", probe)
        os.replace(staging_dir, attempt_dir)
        state = {
            "schema_version": "generation_current_state_v1",
            "updated_at": datetime.now().astimezone().isoformat(),
            "status": status,
            "latest_attempt": attempt_name,
            "model": config.model,
            "reason": reason,
            "online_calls_allowed": status == "passed",
            "api_key_saved": False,
        }
        write_json_atomic(generation_dir / "current_state.json", state)
        return result
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise
