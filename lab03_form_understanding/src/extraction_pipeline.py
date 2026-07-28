from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .model_client import VisionCallResult
from .response_parser import ModelResponseError, parse_model_response
from .result_store import safe_error_message, write_json_atomic
from .schemas import PROMPT_VERSION, SCHEMA_VERSION


def _new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")


def run_extraction(
    *,
    sample_id: str,
    image_path: Path,
    client: Any,
    results_dir: Path,
    update_current: bool,
    secrets: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Call, preserve raw text, validate, and only then optionally update current."""

    run_id = _new_run_id()
    run_at = datetime.now(timezone.utc).isoformat()
    raw_path = results_dir / "history" / "raw" / f"{sample_id}_{run_id}.json"
    parsed_path = results_dir / "history" / "parsed" / f"{sample_id}_{run_id}.json"
    failure_path = results_dir / "failed" / f"{sample_id}_{run_id}.json"

    try:
        call_result: VisionCallResult = client.extract(image_path)
    except Exception as error:
        write_json_atomic(
            failure_path,
            {
                "sample_id": sample_id,
                "run_id": run_id,
                "run_at": run_at,
                "failure_stage": "model_call",
                "error_type": type(error).__name__,
                "message": safe_error_message(error, secrets),
            },
        )
        raise

    raw_payload = {
        "sample_id": sample_id,
        "run_id": run_id,
        "run_at": run_at,
        "model_requested": call_result.requested_model,
        "model_returned": call_result.returned_model,
        "prompt_version": PROMPT_VERSION,
        "finish_reason": call_result.finish_reason,
        "usage": call_result.usage,
        "elapsed_seconds": call_result.elapsed_seconds,
        "response_text": call_result.response_text,
    }
    write_json_atomic(raw_path, raw_payload)

    try:
        parsed = parse_model_response(call_result.response_text)
    except ModelResponseError as error:
        write_json_atomic(
            failure_path,
            {
                "sample_id": sample_id,
                "run_id": run_id,
                "run_at": run_at,
                "failure_stage": error.stage,
                "error_type": type(error).__name__,
                "message": safe_error_message(error, secrets),
                "raw_response_file": str(raw_path),
            },
        )
        raise

    parsed_payload = {
        "metadata": {
            "sample_id": sample_id,
            "run_id": run_id,
            "model": call_result.returned_model,
            "prompt_version": PROMPT_VERSION,
            "schema_version": SCHEMA_VERSION,
            "run_at": run_at,
            "elapsed_seconds": call_result.elapsed_seconds,
            "raw_response_file": str(raw_path),
        },
        "result": parsed.model_dump(mode="json"),
    }
    write_json_atomic(parsed_path, parsed_payload)
    current_path: Path | None = None
    if update_current:
        current_path = results_dir / "current" / f"{sample_id}.json"
        write_json_atomic(current_path, parsed_payload)

    return {
        "run_id": run_id,
        "raw_path": raw_path,
        "parsed_path": parsed_path,
        "current_path": current_path,
        "response_text": call_result.response_text,
        "model": call_result.returned_model,
        "finish_reason": call_result.finish_reason,
        "elapsed_seconds": call_result.elapsed_seconds,
        "usage": call_result.usage,
        "parsed": parsed,
    }
