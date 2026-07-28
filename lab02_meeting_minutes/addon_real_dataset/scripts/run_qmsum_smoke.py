from __future__ import annotations

import json
import sys
from argparse import ArgumentParser
from pathlib import Path
from time import perf_counter
from typing import Any

from openai import OpenAI


ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from lab02_meeting_minutes.src.budget import ensure_budget_available, record_api_call
from lab02_meeting_minutes.src.config import load_settings, validate_real_api_settings
from lab02_meeting_minutes.src.date_normalizer import normalize_due_date, repair_due_date_raw
from lab02_meeting_minutes.src.evidence_repair import repair_payload_evidence
from lab02_meeting_minutes.src.io_utils import read_text_file, write_json
from lab02_meeting_minutes.src.json_utils import parse_json_object
from lab02_meeting_minutes.src.schemas import SCHEMA_VERSION, MeetingExtractionResult, ProcessingMetadata
from lab02_meeting_minutes.src.validators import VALIDATOR_VERSION, validate_result_against_text


ADDON_PROMPT_VERSION_V1 = "addon_prompt_qmsum_real_meeting_v1_draft"
ADDON_PROMPT_VERSION_V2 = "addon_prompt_qmsum_real_meeting_v2_design_requirement_recall"
ADDON_PROMPT_VERSION_V3 = "addon_prompt_qmsum_real_meeting_v3_general_conservative"
ADDON_PROMPT_VERSION_V4 = "addon_prompt_qmsum_real_meeting_v4_owner_decision_precision"
CASE_ID = "TS3010a"
MEETING_ID = "qmsum_product_val_TS3010a"

SYSTEM_PROMPT = """You are a meeting-minutes extraction assistant.

Extract structured JSON from the provided QMSum English meeting transcript.

Rules:
1. Use only the meeting transcript as evidence. Do not use QMSum query answers as evidence.
2. Output valid JSON only. Do not use Markdown fences.
3. Evidence must be a continuous exact substring from the input transcript.
4. Treat {vocalsound}, {gap}, and {disfmarker} as transcription noise.
5. Brainstorming ideas are not automatically decisions.
6. For this addon experiment, decisions mean accepted product design requirements.
7. Only include a design requirement in decisions when it is accepted, repeated, summarized, or supported by multi-speaker discussion.
8. Do not create action_items unless the transcript clearly states an owner and a concrete deliverable. Missing due dates must be null.
9. Do not turn "Next instructions you'll get in your email" into an action item.
10. Open questions should only include explicit unresolved matters.
11. Speaker role labels such as Project Manager, Industrial Designer, Marketing, and User Interface can be attendee names.

Required top-level JSON shape:
{
  "meeting_title": "string",
  "attendees": [{"name": "string", "role": null, "evidence": "string"}],
  "topics": [{"topic_id": "T001", "topic": "string", "evidence": "string"}],
  "decisions": [{"decision_id": "D001", "decision": "string", "evidence": "string"}],
  "action_items": [{"action_id": "A001", "task": "string", "owner": null, "due_date_raw": null, "due_date_normalized": null, "status": "pending", "evidence": "string"}],
  "open_questions": [{"question_id": "Q001", "question": "string", "owner": null, "evidence": "string"}],
  "meeting_summary": "string"
}

If there are no action_items or open_questions, output [] for those arrays.
Set due_date_normalized to null; deterministic code handles date normalization.
Do not output processing_metadata.
"""

SYSTEM_PROMPT_V2 = """You are a meeting-minutes extraction assistant.

Extract structured JSON from the provided QMSum English meeting transcript.

This is a real, noisy, early-stage product design meeting. The goal is to extract accepted product design requirements from the transcript, not to summarize QMSum query answers.

Strict rules:
1. Use only the Meeting Transcript lines as evidence. Do not use QMSum topics, QMSum queries, or QMSum answers as evidence.
2. Evidence must be one exact continuous substring from one transcript bullet line. Do not join two speakers. Do not remove {vocalsound}, {gap}, or {disfmarker} if they appear inside the chosen evidence span.
3. Evidence should not contain more than one speaker label.
4. Brainstorming ideas are not automatically decisions. For this addon experiment, decisions mean accepted product design requirements or constraints.
5. Include accepted design requirements even when they appear early or late in the meeting. Check the full transcript before finalizing.
6. Specifically look for stated requirements or constraints about: original/trendy/user-friendly goals, selling price and manufacturing budget, weight, button count or button size, drop resistance and material, LED feedback, low-cost material, visual attractiveness, compatibility with existing products, and battery consumption.
7. The categories in rule 6 are search targets, not facts by themselves. Only output a decision if the transcript states it and you can cite exact evidence.
8. Do not create action_items unless the transcript clearly states an owner plus a concrete deliverable. Missing due dates must be null.
9. Do not turn "Next instructions you'll get in your email" into an action item.
10. Open questions should only include explicit unresolved matters.
11. Speaker role labels such as Project Manager, Industrial Designer, Marketing, and User Interface can be attendee names.

Required top-level JSON shape:
{
  "meeting_title": "string",
  "attendees": [{"name": "string", "role": null, "evidence": "string"}],
  "topics": [{"topic_id": "T001", "topic": "string", "evidence": "string"}],
  "decisions": [{"decision_id": "D001", "decision": "string", "evidence": "string"}],
  "action_items": [{"action_id": "A001", "task": "string", "owner": null, "due_date_raw": null, "due_date_normalized": null, "status": "pending", "evidence": "string"}],
  "open_questions": [{"question_id": "Q001", "question": "string", "owner": null, "evidence": "string"}],
  "meeting_summary": "string"
}

If there are no action_items or open_questions, output [] for those arrays.
Set due_date_normalized to null; deterministic code handles date normalization.
Do not output processing_metadata.
"""

SYSTEM_PROMPT_V3 = """You are a meeting-minutes extraction assistant.

Extract structured JSON from the provided QMSum English meeting transcript.

This prompt is domain-general. Do not assume the meeting is a product meeting, academic meeting, committee meeting, or project meeting. Infer the meeting intent from the transcript and use conservative extraction.

Strict rules:
1. Use only the Meeting Transcript lines as evidence. Do not use QMSum topics, QMSum queries, or QMSum answers as evidence.
2. Evidence must be anchored in one transcript bullet line. Do not join two speakers. It is acceptable if deterministic validation ignores transcription noise markers such as {vocalsound}, {gap}, and {disfmarker}, but your evidence should still copy the original words as much as possible.
3. Evidence should not contain more than one speaker label.
4. decisions means confirmed conclusions, choices, constraints, experiment settings, accepted directions, or rules that the meeting treats as a basis for later work. Do not limit decisions to product design requirements.
5. Ideas, hypotheses, "maybe", "what if", "I have an idea", and ordinary suggestions are not decisions unless the group clearly accepts them or uses them as the next basis for work.
6. action_items means explicit follow-up work, experiments, analysis, preparation, implementation, review, or coordination assigned to a named speaker or role. A due date is optional and must be null when absent.
7. In research or technical meetings, "I will run...", "I'm going to work on...", or equivalent first-person commitments can be action_items when the speaker is clear.
8. open_questions means unresolved questions, uncertainties, hypotheses to verify, tradeoffs to revisit, or matters explicitly left for later confirmation.
9. If the meeting intent is unclear, use conservative mode: fewer decisions, only clear action_items, and only explicit open_questions.
10. Speaker labels can contain spaces, such as Project Manager, Professor B, PhD D, Grad A, or User Interface.

Required top-level JSON shape:
{
  "meeting_title": "string",
  "attendees": [{"name": "string", "role": null, "evidence": "string"}],
  "topics": [{"topic_id": "T001", "topic": "string", "evidence": "string"}],
  "decisions": [{"decision_id": "D001", "decision": "string", "evidence": "string"}],
  "action_items": [{"action_id": "A001", "task": "string", "owner": null, "due_date_raw": null, "due_date_normalized": null, "status": "pending", "evidence": "string"}],
  "open_questions": [{"question_id": "Q001", "question": "string", "owner": null, "evidence": "string"}],
  "meeting_summary": "string"
}

If there are no decisions, action_items, or open_questions, output [] for those arrays.
Set due_date_normalized to null; deterministic code handles date normalization.
Do not output processing_metadata.
"""

SYSTEM_PROMPT_V4 = """You are a meeting-minutes extraction assistant.

Extract structured JSON from the provided QMSum English meeting transcript.

This prompt is domain-general. Do not assume the meeting is a product meeting, academic meeting, committee meeting, or project meeting. Infer the meeting intent from the transcript and use conservative extraction.

Strict rules:
1. Use only the Meeting Transcript lines as evidence. Do not use QMSum topics, QMSum queries, or QMSum answers as evidence.
2. Evidence must be copied from exactly one transcript bullet line. Do not join two speakers. Do not use ellipses, "..." placeholders, summaries, or stitched fragments.
3. It is acceptable if deterministic validation ignores transcription noise markers such as {vocalsound}, {gap}, and {disfmarker}, but your evidence should still copy the original line as much as possible.
4. decisions means confirmed conclusions, choices, constraints, experiment settings, accepted directions, or rules that the meeting treats as a basis for later work.
5. Ideas, hypotheses, "maybe", "what if", "I have an idea", "we can try", and "run experiments to see whether" are not decisions unless the transcript clearly says the group accepted them as the plan. If evidence says an experiment is needed to decide, put it in action_items or open_questions, not decisions.
6. action_items means explicit follow-up work, experiments, analysis, preparation, implementation, review, or coordination assigned to a named speaker or role.
7. For every action_item with an owner, the evidence must either include that owner's speaker label or contain the owner name in the same line. If the only evidence is another speaker suggesting work, set owner to null or do not create the action item.
8. In research or technical meetings, first-person commitments such as "I will run...", "I'll try...", or "I'm going to work on..." can be action_items only when the evidence line is spoken by that owner.
9. due_date_raw is optional. Use null when no explicit date or timeframe appears in the evidence. If due_date_raw is filled, it must be an exact substring of the evidence.
10. open_questions means unresolved questions, uncertainties, hypotheses to verify, tradeoffs to revisit, or matters explicitly left for later confirmation.
11. If the meeting intent is unclear, use conservative mode: fewer decisions, only clear action_items, and only explicit open_questions.
12. Speaker labels can contain spaces, such as Project Manager, Professor B, PhD D, Grad A, or User Interface.

Required top-level JSON shape:
{
  "meeting_title": "string",
  "attendees": [{"name": "string", "role": null, "evidence": "string"}],
  "topics": [{"topic_id": "T001", "topic": "string", "evidence": "string"}],
  "decisions": [{"decision_id": "D001", "decision": "string", "evidence": "string"}],
  "action_items": [{"action_id": "A001", "task": "string", "owner": null, "due_date_raw": null, "due_date_normalized": null, "status": "pending", "evidence": "string"}],
  "open_questions": [{"question_id": "Q001", "question": "string", "owner": null, "evidence": "string"}],
  "meeting_summary": "string"
}

If there are no decisions, action_items, or open_questions, output [] for those arrays.
Set due_date_normalized to null; deterministic code handles date normalization.
Do not output processing_metadata.
"""

USER_TEMPLATE = """Meeting ID: {meeting_id}
Meeting date: not provided

Meeting transcript:
{meeting_text}
"""


def main() -> int:
    parser = ArgumentParser()
    parser.add_argument("--prompt", choices=["v1", "v2", "v3", "v4"], default="v4")
    args = parser.parse_args()
    if args.prompt == "v4":
        prompt_version = ADDON_PROMPT_VERSION_V4
        system_prompt = SYSTEM_PROMPT_V4
    elif args.prompt == "v3":
        prompt_version = ADDON_PROMPT_VERSION_V3
        system_prompt = SYSTEM_PROMPT_V3
    elif args.prompt == "v2":
        prompt_version = ADDON_PROMPT_VERSION_V2
        system_prompt = SYSTEM_PROMPT_V2
    else:
        prompt_version = ADDON_PROMPT_VERSION_V1
        system_prompt = SYSTEM_PROMPT
    suffix = f"_{args.prompt}"

    settings = load_settings()
    validate_real_api_settings(settings)
    input_path = ROOT / "data" / "selected_cases" / f"{CASE_ID}.md"
    output_dir = ROOT / "outputs" / "real_smoke"
    output_path = output_dir / f"{CASE_ID}{suffix}_result.json"
    raw_path = output_dir / f"{CASE_ID}{suffix}_raw.json"
    metadata_path = output_dir / f"{CASE_ID}{suffix}_metadata.json"

    started = perf_counter()
    text = read_text_file(input_path)
    ensure_budget_available()
    metadata: dict[str, Any] = {
        "case_id": CASE_ID,
        "meeting_id": MEETING_ID,
        "model": settings.model,
        "prompt_version": prompt_version,
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
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": USER_TEMPLATE.format(meeting_id=MEETING_ID, meeting_text=text)},
            ],
        )
        content = response.choices[0].message.content or ""
        payload = parse_json_object(content)
        write_json(raw_path, json.dumps(payload, ensure_ascii=False, indent=2))
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

    payload["meeting_id"] = MEETING_ID
    payload["meeting_date"] = None
    repair_payload_evidence(payload, text)
    _normalize_action_dates(payload)
    payload["processing_metadata"] = ProcessingMetadata(
        mode="single_pass",
        chunk_count=1,
        model=settings.model,
        prompt_version=prompt_version,
        schema_version=SCHEMA_VERSION,
        validator_version=VALIDATOR_VERSION,
        elapsed_seconds=round(perf_counter() - started, 4),
        usage=metadata.get("usage", {}),
    ).model_dump(mode="json")
    result = MeetingExtractionResult.model_validate(payload)
    validation = validate_result_against_text(result, text)
    result.validation_issues.extend(validation.issues)
    write_json(output_path, json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
    write_json(metadata_path, json.dumps(metadata, ensure_ascii=False, indent=2))
    print(json.dumps({"ok": not result.validation_issues, "output": str(output_path), "validation_issue_count": len(result.validation_issues), "api_budget_used": metadata["api_budget_used"]}, ensure_ascii=False, indent=2))
    return 0 if not result.validation_issues else 2


def _normalize_action_dates(payload: dict[str, Any]) -> None:
    for action in payload.get("action_items", []):
        action["due_date_raw"] = repair_due_date_raw(action.get("due_date_raw"), action.get("evidence"))
        action["due_date_normalized"] = normalize_due_date(action.get("due_date_raw"), None)


if __name__ == "__main__":
    raise SystemExit(main())
