from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter
from typing import Literal

from .chunking import chunk_by_turns
from .config import Settings
from .date_normalizer import normalize_due_date, repair_due_date_raw
from .evidence_repair import repair_payload_evidence
from .io_utils import infer_meeting_date, infer_meeting_id, read_text_file, write_json
from .mock_client import MockLLMClient
from .prompts import PROMPT_VERSION
from .real_client import RealLLMClient
from .schemas import SCHEMA_VERSION, MeetingExtractionResult, ProcessingMetadata
from .validators import VALIDATOR_VERSION, validate_result_against_text


PROJECT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_DIR / "data"


def run_mock_pipeline(input_path: Path, output_path: Path, settings: Settings, meeting_date: str | None = None, force_mode: Literal["single_pass", "chunked"] | None = None) -> MeetingExtractionResult:
    started = perf_counter()
    text = read_text_file(input_path)
    resolved_meeting_date = meeting_date if meeting_date is not None else infer_meeting_date(text)
    meeting_id = infer_meeting_id(input_path, text)
    mode, chunk_count = _choose_mode(text, settings.chunk_max_chars, settings.chunk_overlap_turns, force_mode)
    payload = MockLLMClient(DATA_DIR).extract(meeting_id, text, resolved_meeting_date)
    _normalize_action_dates(payload, resolved_meeting_date)
    repair_payload_evidence(payload, text)
    payload["processing_metadata"] = ProcessingMetadata(mode=mode, chunk_count=chunk_count, model="mock", prompt_version=PROMPT_VERSION, schema_version=SCHEMA_VERSION, validator_version=VALIDATOR_VERSION, elapsed_seconds=round(perf_counter() - started, 4), usage={}).model_dump(mode="json")
    result = MeetingExtractionResult.model_validate(payload)
    report = validate_result_against_text(result, text)
    result.validation_issues.extend(report.issues)
    write_json(output_path, json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return result


def run_real_pipeline(input_path: Path, output_path: Path, settings: Settings, meeting_date: str | None = None, force_mode: Literal["single_pass", "chunked"] | None = None) -> MeetingExtractionResult:
    started = perf_counter()
    text = read_text_file(input_path)
    resolved_meeting_date = meeting_date if meeting_date is not None else infer_meeting_date(text)
    meeting_id = infer_meeting_id(input_path, text)
    mode, chunk_count = _choose_mode(text, settings.chunk_max_chars, settings.chunk_overlap_turns, force_mode)
    if mode == "chunked":
        raise NotImplementedError("real API chunked mode is not enabled before H3 freeze")
    payload, call_metadata = RealLLMClient(settings).extract(meeting_id, text, resolved_meeting_date)
    write_json(output_path.with_name(output_path.stem + "_raw.json"), json.dumps(payload, ensure_ascii=False, indent=2))
    _normalize_action_dates(payload, resolved_meeting_date)
    payload["meeting_id"] = meeting_id
    payload["meeting_date"] = resolved_meeting_date
    payload["processing_metadata"] = ProcessingMetadata(mode=mode, chunk_count=chunk_count, model=settings.model, prompt_version=PROMPT_VERSION, schema_version=SCHEMA_VERSION, validator_version=VALIDATOR_VERSION, elapsed_seconds=round(perf_counter() - started, 4), usage=call_metadata.get("usage", {})).model_dump(mode="json")
    repair_payload_evidence(payload, text)
    result = MeetingExtractionResult.model_validate(payload)
    report = validate_result_against_text(result, text)
    result.validation_issues.extend(report.issues)
    write_json(output_path, json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return result


def _choose_mode(text: str, max_chars: int, overlap_turns: int, force_mode: Literal["single_pass", "chunked"] | None) -> tuple[str, int]:
    if force_mode == "single_pass":
        return "single_pass", 1
    if force_mode == "chunked" or len(text) > max_chars:
        return "chunked", len(chunk_by_turns(text, max_chars=max_chars, overlap_turns=overlap_turns))
    return "single_pass", 1


def _normalize_action_dates(payload: dict, meeting_date: str | None) -> None:
    for action in payload.get("action_items", []):
        action["due_date_raw"] = repair_due_date_raw(action.get("due_date_raw"), action.get("evidence"))
        action["due_date_normalized"] = normalize_due_date(action.get("due_date_raw"), meeting_date)
