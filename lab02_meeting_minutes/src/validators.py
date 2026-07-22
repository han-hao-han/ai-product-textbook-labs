from __future__ import annotations

import re
from dataclasses import dataclass

from .schemas import ActionItem, Decision, MeetingExtractionResult, OpenQuestion, ValidationIssue


VALIDATOR_VERSION = "validator_v2_noise_tolerant_evidence"
SPEAKER_RE = re.compile(
    r"^\s*(?:[-*]\s*)?(?:\[([\u4e00-\u9fa5A-Za-z0-9_][\u4e00-\u9fa5A-Za-z0-9_ .-]{0,39})\]|([\u4e00-\u9fa5A-Za-z0-9_][\u4e00-\u9fa5A-Za-z0-9_ .-]{0,39})\s*[:：]|([\u4e00-\u9fa5]{1,8})\s*-\s*)",
    re.MULTILINE,
)
TRANSCRIPT_NOISE_RE = re.compile(r"\{(?:vocalsound|gap|disfmarker)\}", re.IGNORECASE)
RESERVED_LABELS = {"数据类型", "会议标题", "会议日期", "说话人", "会议转写"}


@dataclass(frozen=True)
class ValidationReport:
    ok: bool
    issues: list[ValidationIssue]


def normalize_text(text: str) -> str:
    without_noise = TRANSCRIPT_NOISE_RE.sub("", text)
    return "".join(without_noise.split())


def extract_speaker_names(text: str) -> set[str]:
    names: set[str] = set()
    for bracket_name, delimiter_name, dash_name in SPEAKER_RE.findall(text):
        name = bracket_name or delimiter_name or dash_name
        name = name.strip()
        if name not in RESERVED_LABELS:
            names.add(name)
    return names


def evidence_exists(text: str, evidence: str) -> bool:
    return normalize_text(evidence) in normalize_text(text)


def validate_result_against_text(result: MeetingExtractionResult, source_text: str) -> ValidationReport:
    issues: list[ValidationIssue] = []
    speakers = extract_speaker_names(source_text)
    for item in [*result.topics, *result.decisions, *result.action_items, *result.open_questions]:
        item_id = getattr(item, "topic_id", None) or getattr(item, "decision_id", None) or getattr(item, "action_id", None) or getattr(item, "question_id", None)
        if not evidence_exists(source_text, item.evidence):
            issues.append(ValidationIssue(code="evidence_not_found", message="证据无法在原文中定位", item_id=item_id))
    for action in result.action_items:
        issues.extend(_validate_action(action, source_text, speakers))
    issues.extend(_validate_decision_question_conflicts(result.decisions, result.open_questions))
    return ValidationReport(ok=not any(issue.severity == "error" for issue in issues), issues=issues)


def _validate_action(action: ActionItem, source_text: str, speakers: set[str]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    owners = action.owner if isinstance(action.owner, list) else ([action.owner] if action.owner else [])
    for owner in owners:
        if owner not in speakers:
            issues.append(ValidationIssue(code="owner_not_in_speakers", message=f"负责人 {owner} 不在说话人列表中", item_id=action.action_id))
        if owner not in action.evidence and not _evidence_spoken_by_owner(source_text, action.evidence, owner):
            issues.append(ValidationIssue(code="owner_not_in_evidence", message=f"负责人 {owner} 未出现在行动项证据中", item_id=action.action_id))
    if action.due_date_raw and not evidence_exists(source_text, action.due_date_raw):
        issues.append(ValidationIssue(code="due_date_raw_not_found", message="原始截止日期无法在原文中定位", item_id=action.action_id))
    if action.due_date_raw is None and action.due_date_normalized is not None:
        issues.append(ValidationIssue(code="normalized_date_without_raw", message="缺少原始日期时不得生成规范日期", item_id=action.action_id))
    return issues


def _evidence_spoken_by_owner(source_text: str, evidence: str, owner: str) -> bool:
    normalized_evidence = normalize_text(evidence)
    for line in source_text.splitlines():
        if normalized_evidence not in normalize_text(line):
            continue
        match = SPEAKER_RE.match(line)
        if not match:
            continue
        speaker = match.group(1) or match.group(2)
        if speaker == owner:
            return True
    return False


def _validate_decision_question_conflicts(decisions: list[Decision], questions: list[OpenQuestion]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    decision_texts = [normalize_text(item.decision) for item in decisions]
    for question in questions:
        q_text = normalize_text(question.question)
        if any(q_text and (q_text in decision or decision in q_text) for decision in decision_texts):
            issues.append(ValidationIssue(code="decision_open_question_conflict", message="同一事项同时出现在决策和未决问题中", item_id=question.question_id))
    return issues
