from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal


ComparedKind = Literal["action_items", "decisions", "open_questions"]
GOLD_COMPARE_VERSION = "gold_compare_v1_h3_draft"


@dataclass(frozen=True)
class CompareIssue:
    kind: ComparedKind
    code: Literal["missing_gold_item", "unexpected_result_item"]
    gold_id: str | None
    result_id: str | None
    message: str
    gold_text: str | None = None
    result_text: str | None = None


@dataclass(frozen=True)
class CompareReport:
    ok: bool
    issues: list[CompareIssue]

    def model_dump(self) -> dict[str, Any]:
        return {"gold_compare_version": GOLD_COMPARE_VERSION, "ok": self.ok, "issues": [issue.__dict__ for issue in self.issues]}


def compare_gold_file(gold_path: Path, result_path: Path) -> CompareReport:
    gold = json.loads(gold_path.read_text(encoding="utf-8"))
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if "cases" in gold:
        return compare_case_gold(gold, result)
    return compare_main_gold(gold, result)


def compare_main_gold(gold: dict[str, Any], result: dict[str, Any]) -> CompareReport:
    issues: list[CompareIssue] = []
    for kind in ["action_items", "decisions", "open_questions"]:
        issues.extend(_compare_collection(kind, gold.get(kind, []), result.get(kind, [])))
    return CompareReport(ok=not issues, issues=issues)


def compare_case_gold(gold: dict[str, Any], result: dict[str, Any]) -> CompareReport:
    meeting_id = result.get("meeting_id")
    case = _find_gold_case(gold, meeting_id)
    issues: list[CompareIssue] = []
    issues.extend(_compare_collection("action_items", _with_generated_ids("action_items", case.get("expected_action_items", [])), result.get("action_items", [])))
    issues.extend(_compare_collection("decisions", _with_generated_ids("decisions", case.get("expected_decisions", [])), result.get("decisions", [])))
    issues.extend(_compare_collection("open_questions", _with_generated_ids("open_questions", case.get("expected_open_questions", [])), result.get("open_questions", [])))
    return CompareReport(ok=not issues, issues=issues)


def _find_gold_case(gold: dict[str, Any], meeting_id: str | None) -> dict[str, Any]:
    for case in gold.get("cases", []):
        if case.get("meeting_id") == meeting_id:
            return case
    raise ValueError(f"no gold case found for meeting_id: {meeting_id}")


def _with_generated_ids(kind: ComparedKind, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prefix = {"action_items": "A", "decisions": "D", "open_questions": "Q"}[kind]
    id_key = {"action_items": "action_id", "decisions": "decision_id", "open_questions": "question_id"}[kind]
    return [{id_key: item.get(id_key, f"{prefix}{index:03d}"), **item} for index, item in enumerate(items, start=1)]


def _compare_collection(kind: ComparedKind, gold_items: list[dict[str, Any]], result_items: list[dict[str, Any]]) -> list[CompareIssue]:
    issues: list[CompareIssue] = []
    matched_result_indexes: set[int] = set()
    for gold_item in gold_items:
        match_index = _find_match(kind, gold_item, result_items, matched_result_indexes)
        if match_index is None:
            issues.append(
                CompareIssue(
                    kind=kind,
                    code="missing_gold_item",
                    gold_id=_item_id(kind, gold_item),
                    result_id=None,
                    message=f"金标准 {kind} 条目未在结果中匹配到",
                    gold_text=_semantic_text(kind, gold_item),
                )
            )
        else:
            matched_result_indexes.add(match_index)
    for index, result_item in enumerate(result_items):
        if index in matched_result_indexes:
            continue
        issues.append(
            CompareIssue(
                kind=kind,
                code="unexpected_result_item",
                gold_id=None,
                result_id=_item_id(kind, result_item),
                message=f"结果中存在未匹配金标准的 {kind} 条目",
                result_text=_semantic_text(kind, result_item),
            )
        )
    return issues


def _find_match(kind: ComparedKind, gold_item: dict[str, Any], result_items: list[dict[str, Any]], used_indexes: set[int]) -> int | None:
    for index, result_item in enumerate(result_items):
        if index in used_indexes:
            continue
        if _items_match(kind, gold_item, result_item):
            return index
    return None


def _items_match(kind: ComparedKind, gold_item: dict[str, Any], result_item: dict[str, Any]) -> bool:
    if kind == "action_items":
        return _action_matches(gold_item, result_item)
    return _text_matches(_semantic_text(kind, gold_item), _semantic_text(kind, result_item)) or _evidence_matches(gold_item, result_item)


def _action_matches(gold_item: dict[str, Any], result_item: dict[str, Any]) -> bool:
    if not _owner_matches(gold_item.get("owner"), result_item.get("owner")):
        return False
    if gold_item.get("due_date_normalized") != result_item.get("due_date_normalized"):
        return False
    return _text_matches(str(gold_item.get("task", "")), str(result_item.get("task", ""))) or _evidence_matches(gold_item, result_item)


def _owner_matches(gold_owner: Any, result_owner: Any) -> bool:
    return _owner_set(gold_owner) == _owner_set(result_owner)


def _owner_set(owner: Any) -> tuple[str, ...]:
    if owner is None:
        return ()
    if isinstance(owner, list):
        return tuple(sorted(str(item) for item in owner))
    return (str(owner),)


def _evidence_matches(gold_item: dict[str, Any], result_item: dict[str, Any]) -> bool:
    return _text_matches(str(gold_item.get("evidence", "")), str(result_item.get("evidence", "")))


def _text_matches(left: str, right: str) -> bool:
    normalized_left = _normalize(left)
    normalized_right = _normalize(right)
    if not normalized_left or not normalized_right:
        return False
    if normalized_left in normalized_right or normalized_right in normalized_left:
        return True
    overlap = _character_overlap(normalized_left, normalized_right)
    if overlap >= 0.72:
        return True
    coverage = _character_coverage(normalized_left, normalized_right)
    if coverage >= 0.7:
        return True
    return _sequence_similarity(normalized_left, normalized_right) >= 0.72


def _character_coverage(left: str, right: str) -> float:
    left_chars = set(left)
    right_chars = set(right)
    shorter = min(len(left_chars), len(right_chars))
    if shorter == 0:
        return 0
    return len(left_chars & right_chars) / shorter


def _character_overlap(left: str, right: str) -> float:
    left_chars = set(left)
    right_chars = set(right)
    if not left_chars or not right_chars:
        return 0
    return len(left_chars & right_chars) / len(left_chars | right_chars)


def _sequence_similarity(left: str, right: str) -> float:
    shorter = min(len(left), len(right))
    if shorter == 0:
        return 0
    return _longest_common_subsequence_len(left, right) / shorter


def _longest_common_subsequence_len(left: str, right: str) -> int:
    previous = [0] * (len(right) + 1)
    for left_char in left:
        current = [0]
        for index, right_char in enumerate(right, start=1):
            if left_char == right_char:
                current.append(previous[index - 1] + 1)
            else:
                current.append(max(previous[index], current[-1]))
        previous = current
    return previous[-1]


def _normalize(value: str) -> str:
    punctuation = " \t\r\n，。；：！？、“”‘’（）()[]【】《》<>-—_"
    return "".join(char for char in value if char not in punctuation)


def _semantic_text(kind: ComparedKind, item: dict[str, Any]) -> str:
    if kind == "action_items":
        return str(item.get("task", ""))
    if kind == "decisions":
        return str(item.get("decision", ""))
    return str(item.get("question", ""))


def _item_id(kind: ComparedKind, item: dict[str, Any]) -> str | None:
    if kind == "action_items":
        return item.get("action_id")
    if kind == "decisions":
        return item.get("decision_id")
    return item.get("question_id")
