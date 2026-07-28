from __future__ import annotations

import json
import sys
from pathlib import Path
from time import perf_counter

from openai import OpenAI


ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lab02_meeting_minutes.addon_real_dataset.scripts.run_qmsum_smoke import ADDON_PROMPT_VERSION_V4, SYSTEM_PROMPT_V4, USER_TEMPLATE
from lab02_meeting_minutes.src.budget import ensure_budget_available, record_api_call
from lab02_meeting_minutes.src.config import Settings, validate_real_api_settings
from lab02_meeting_minutes.src.date_normalizer import normalize_due_date, repair_due_date_raw
from lab02_meeting_minutes.src.evidence_repair import repair_payload_evidence
from lab02_meeting_minutes.src.io_utils import infer_meeting_id, read_text_file, write_json
from lab02_meeting_minutes.src.json_utils import parse_json_object
from lab02_meeting_minutes.src.schemas import SCHEMA_VERSION, MeetingExtractionResult, ProcessingMetadata
from lab02_meeting_minutes.src.validators import VALIDATOR_VERSION, validate_result_against_text


def run_qmsum_real_pipeline(input_path: Path, output_path: Path, settings: Settings) -> MeetingExtractionResult:
    started = perf_counter()
    text = read_text_file(input_path)
    meeting_id = infer_meeting_id(input_path, text)
    validate_real_api_settings(settings)
    ensure_budget_available()
    metadata = {
        "meeting_id": meeting_id,
        "model": settings.model,
        "prompt_version": ADDON_PROMPT_VERSION_V4,
        "schema_version": SCHEMA_VERSION,
        "validator_version": VALIDATOR_VERSION,
        "status": "started",
        "usage": {},
    }
    try:
        client = OpenAI(api_key=settings.api_key, base_url=settings.base_url, timeout=settings.timeout_seconds)
        response = client.chat.completions.create(
            model=settings.model,
            temperature=settings.temperature,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT_V4},
                {"role": "user", "content": USER_TEMPLATE.format(meeting_id=meeting_id, meeting_text=text)},
            ],
        )
        payload = parse_json_object(response.choices[0].message.content or "")
        write_json(output_path.with_name(output_path.stem + "_raw.json"), json.dumps(payload, ensure_ascii=False, indent=2))
        if response.usage is not None:
            metadata["usage"] = response.usage.model_dump()
        metadata["status"] = "success"
    except Exception as exc:
        metadata["status"] = "failed"
        metadata["error_type"] = type(exc).__name__
        metadata["error_message"] = str(exc)
        raise
    finally:
        budget = record_api_call()
        metadata["api_budget_used"] = budget["used"]
        metadata["api_budget_remaining"] = budget["remaining"]

    payload["meeting_id"] = meeting_id
    payload["meeting_date"] = None
    repair_payload_evidence(payload, text)
    _normalize_action_dates(payload)
    payload["processing_metadata"] = ProcessingMetadata(
        mode="single_pass",
        chunk_count=1,
        model=settings.model,
        prompt_version=ADDON_PROMPT_VERSION_V4,
        schema_version=SCHEMA_VERSION,
        validator_version=VALIDATOR_VERSION,
        elapsed_seconds=round(perf_counter() - started, 4),
        usage=metadata.get("usage", {}),
    ).model_dump(mode="json")
    result = MeetingExtractionResult.model_validate(payload)
    validation = validate_result_against_text(result, text)
    result.validation_issues.extend(validation.issues)
    write_json(output_path, json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
    write_json(output_path.with_name(output_path.stem + "_metadata.json"), json.dumps(metadata, ensure_ascii=False, indent=2))
    return result


def _normalize_action_dates(payload: dict) -> None:
    for action in payload.get("action_items", []):
        action["due_date_raw"] = repair_due_date_raw(action.get("due_date_raw"), action.get("evidence"))
        action["due_date_normalized"] = normalize_due_date(action.get("due_date_raw"), None)
