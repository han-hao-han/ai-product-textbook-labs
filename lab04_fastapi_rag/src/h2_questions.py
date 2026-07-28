from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .io_utils import read_json, sha256_file


HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SCOPES = {"in_scope", "boundary", "out_of_scope"}
ANSWER_TYPES = {
    "concise_concept",
    "procedure",
    "code_example",
    "comprehensive",
}
GROUPS = {"tutorial", "advanced", "deployment", "how-to"}


@dataclass(frozen=True)
class SourceGroup:
    group_id: str
    paths: tuple[str, ...]


@dataclass(frozen=True)
class H2Question:
    question_id: str
    scope: str
    question_type: str
    document_group: str | None
    question: str
    required_points: tuple[str, ...]
    optional_points: tuple[str, ...]
    critical_errors: tuple[str, ...]
    acceptable_source_groups: tuple[SourceGroup, ...]
    related_corpus_paths: tuple[str, ...]
    expected_behavior: str
    contains_short_python_code: bool


@dataclass(frozen=True)
class H2QuestionSet:
    path: Path
    set_id: str
    set_role: str
    review_status: str
    source_commit: str
    corpus_sha256: str
    questions: tuple[H2Question, ...]

    @property
    def sha256(self) -> str:
        return sha256_file(self.path)


def _string_list(value: Any, field: str, *, allow_empty: bool) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{field}必须是数组")
    items = tuple(str(item).strip() for item in value)
    if (not allow_empty and not items) or any(not item for item in items):
        raise ValueError(f"{field}包含空值或缺少条目")
    if len(set(items)) != len(items):
        raise ValueError(f"{field}包含重复条目")
    return items


def load_h2_question_set(path: Path) -> H2QuestionSet:
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise ValueError("H2题集必须是JSON对象")
    required = {
        "schema_version",
        "set_id",
        "set_role",
        "review_status",
        "source_commit",
        "corpus_sha256",
        "questions",
    }
    missing = sorted(required - payload.keys())
    if missing:
        raise ValueError(f"H2题集缺少字段：{', '.join(missing)}")
    if payload["schema_version"] != "h2_question_set_v1":
        raise ValueError("不支持的H2题集版本")
    role = str(payload["set_role"])
    if role not in {"calibration", "evaluation"}:
        raise ValueError("set_role必须是calibration或evaluation")
    status = str(payload["review_status"])
    if status not in {
        "candidate_pending_h2_confirmation",
        "h2_frozen_user_confirmed",
    }:
        raise ValueError("H2题集review_status无效")
    commit = str(payload["source_commit"])
    corpus_sha256 = str(payload["corpus_sha256"])
    if not COMMIT_PATTERN.fullmatch(commit):
        raise ValueError("H2题集source_commit无效")
    if not HASH_PATTERN.fullmatch(corpus_sha256):
        raise ValueError("H2题集corpus_sha256无效")
    raw_questions = payload["questions"]
    if not isinstance(raw_questions, list) or not raw_questions:
        raise ValueError("H2题集questions必须是非空数组")

    questions: list[H2Question] = []
    ids: set[str] = set()
    texts: set[str] = set()
    for raw in raw_questions:
        if not isinstance(raw, dict):
            raise ValueError("H2题目必须是JSON对象")
        question_id = str(raw.get("question_id", "")).strip()
        scope = str(raw.get("scope", "")).strip()
        question_type = str(raw.get("question_type", "")).strip()
        document_group_raw = raw.get("document_group")
        document_group = (
            str(document_group_raw).strip()
            if document_group_raw is not None
            else None
        )
        question = str(raw.get("question", "")).strip()
        expected_behavior = str(raw.get("expected_behavior", "")).strip()
        contains_code = raw.get("contains_short_python_code")
        if not question_id or question_id in ids:
            raise ValueError(f"H2题目ID为空或重复：{question_id}")
        if not question or question in texts or len(question) > 2000:
            raise ValueError(f"H2问题为空、重复或超过2000字符：{question_id}")
        if scope not in SCOPES:
            raise ValueError(f"H2 scope无效：{question_id}")
        if not isinstance(contains_code, bool):
            raise ValueError(f"contains_short_python_code必须是布尔值：{question_id}")
        required_points = _string_list(
            raw.get("required_points"),
            f"{question_id}.required_points",
            allow_empty=False,
        )
        optional_points = _string_list(
            raw.get("optional_points"),
            f"{question_id}.optional_points",
            allow_empty=True,
        )
        critical_errors = _string_list(
            raw.get("critical_errors"),
            f"{question_id}.critical_errors",
            allow_empty=False,
        )
        raw_groups = raw.get("acceptable_source_groups")
        if not isinstance(raw_groups, list):
            raise ValueError(f"acceptable_source_groups必须是数组：{question_id}")
        source_groups: list[SourceGroup] = []
        seen_group_ids: set[str] = set()
        for raw_group in raw_groups:
            if not isinstance(raw_group, dict):
                raise ValueError(f"来源组必须是JSON对象：{question_id}")
            group_id = str(raw_group.get("group_id", "")).strip()
            if not group_id or group_id in seen_group_ids:
                raise ValueError(f"来源组ID为空或重复：{question_id}")
            paths = _string_list(
                raw_group.get("paths"),
                f"{question_id}.{group_id}.paths",
                allow_empty=False,
            )
            seen_group_ids.add(group_id)
            source_groups.append(SourceGroup(group_id, paths))
        related_paths = _string_list(
            raw.get("related_corpus_paths", []),
            f"{question_id}.related_corpus_paths",
            allow_empty=True,
        )

        if scope == "in_scope":
            if question_type not in ANSWER_TYPES:
                raise ValueError(f"库内题型无效：{question_id}")
            if document_group not in GROUPS:
                raise ValueError(f"库内文档组无效：{question_id}")
            if expected_behavior != "answered" or not source_groups:
                raise ValueError(f"库内题必须answered且有可接受来源：{question_id}")
            if related_paths:
                raise ValueError(f"库内题不得配置related_corpus_paths：{question_id}")
        else:
            if (
                question_type != "not_applicable"
                or document_group is not None
                or expected_behavior != "refused"
                or source_groups
            ):
                raise ValueError(
                    f"边界/库外题必须not_applicable、无文档组、refused且无可接受来源："
                    f"{question_id}"
                )
            if contains_code:
                raise ValueError(f"边界/库外题不得要求短代码：{question_id}")

        ids.add(question_id)
        texts.add(question)
        questions.append(
            H2Question(
                question_id=question_id,
                scope=scope,
                question_type=question_type,
                document_group=document_group,
                question=question,
                required_points=required_points,
                optional_points=optional_points,
                critical_errors=critical_errors,
                acceptable_source_groups=tuple(source_groups),
                related_corpus_paths=related_paths,
                expected_behavior=expected_behavior,
                contains_short_python_code=contains_code,
            )
        )
    return H2QuestionSet(
        path=path,
        set_id=str(payload["set_id"]),
        set_role=role,
        review_status=status,
        source_commit=commit,
        corpus_sha256=corpus_sha256,
        questions=tuple(questions),
    )


def load_gate_policy(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise ValueError("门控策略必须是JSON对象")
    if payload.get("schema_version") != "retrieval_gate_policy_v1":
        raise ValueError("不支持的门控策略版本")
    if payload.get("review_status") not in {
        "candidate_pending_h2_confirmation",
        "h2_frozen_user_confirmed",
    }:
        raise ValueError("门控策略review_status无效")
    if payload.get("threshold") is not None:
        raise ValueError("H2候选阶段不得预填正式阈值")
    algorithm = payload.get("algorithm")
    if not isinstance(algorithm, dict):
        raise ValueError("门控策略缺少algorithm")
    if float(algorithm.get("minimum_in_scope_recall", -1)) != 0.9:
        raise ValueError("门控最低库内召回必须为0.9")
    return payload


def audit_h2_question_sets(
    calibration: H2QuestionSet,
    evaluation: H2QuestionSet,
    gate_policy: dict[str, Any],
    *,
    included_paths: set[str],
    source_commit: str,
    corpus_sha256: str,
) -> dict[str, Any]:
    if calibration.set_role != "calibration":
        raise ValueError("校准题文件的set_role错误")
    if evaluation.set_role != "evaluation":
        raise ValueError("正式题文件的set_role错误")
    for question_set in (calibration, evaluation):
        if question_set.source_commit != source_commit:
            raise ValueError(f"{question_set.set_id}的Commit与当前运行不一致")
        if question_set.corpus_sha256 != corpus_sha256:
            raise ValueError(f"{question_set.set_id}的语料哈希与当前运行不一致")
    if gate_policy.get("calibration_set_id") != calibration.set_id:
        raise ValueError("门控策略引用的校准集ID不一致")
    if gate_policy.get("evaluation_set_id") != evaluation.set_id:
        raise ValueError("门控策略引用的正式集ID不一致")

    calibration_scope = Counter(item.scope for item in calibration.questions)
    evaluation_scope = Counter(item.scope for item in evaluation.questions)
    if calibration_scope != {
        "in_scope": 20,
        "boundary": 10,
        "out_of_scope": 20,
    }:
        raise ValueError(f"校准集范围配额错误：{dict(calibration_scope)}")
    if evaluation_scope != {
        "in_scope": 18,
        "boundary": 6,
        "out_of_scope": 6,
    }:
        raise ValueError(f"正式集范围配额错误：{dict(evaluation_scope)}")

    evaluation_in_scope = [
        item for item in evaluation.questions if item.scope == "in_scope"
    ]
    group_counts = Counter(item.document_group for item in evaluation_in_scope)
    if group_counts != {
        "tutorial": 9,
        "advanced": 4,
        "deployment": 3,
        "how-to": 2,
    }:
        raise ValueError(f"正式集文档组配额错误：{dict(group_counts)}")
    type_counts = Counter(item.question_type for item in evaluation_in_scope)
    if type_counts != {
        "concise_concept": 4,
        "procedure": 5,
        "code_example": 5,
        "comprehensive": 4,
    }:
        raise ValueError(f"正式集题型配额错误：{dict(type_counts)}")
    code_count = sum(item.contains_short_python_code for item in evaluation_in_scope)
    if code_count < 4:
        raise ValueError("正式集至少4题必须要求短Python代码")

    all_ids: set[str] = set()
    all_texts: set[str] = set()
    referenced_paths: set[str] = set()
    for question_set in (calibration, evaluation):
        for item in question_set.questions:
            if item.question_id in all_ids or item.question in all_texts:
                raise ValueError("校准集与正式集之间存在重复ID或问题文本")
            all_ids.add(item.question_id)
            all_texts.add(item.question)
            for group in item.acceptable_source_groups:
                referenced_paths.update(group.paths)
            referenced_paths.update(item.related_corpus_paths)
    unknown_paths = sorted(referenced_paths - included_paths)
    if unknown_paths:
        raise ValueError(f"H2题集引用未纳入语料的路径：{unknown_paths}")

    return {
        "schema_version": "h2_candidate_audit_v1",
        "status": "passed",
        "review_status": "candidate_pending_h2_confirmation",
        "source_commit": source_commit,
        "corpus_sha256": corpus_sha256,
        "calibration": {
            "set_id": calibration.set_id,
            "question_count": len(calibration.questions),
            "scope_counts": dict(sorted(calibration_scope.items())),
            "sha256": calibration.sha256,
        },
        "evaluation": {
            "set_id": evaluation.set_id,
            "question_count": len(evaluation.questions),
            "scope_counts": dict(sorted(evaluation_scope.items())),
            "document_group_counts": dict(sorted(group_counts.items())),
            "question_type_counts": dict(sorted(type_counts.items())),
            "questions_with_short_python_code": code_count,
            "sha256": evaluation.sha256,
        },
        "referenced_included_paths": len(referenced_paths),
        "gate_policy": {
            "status": gate_policy["review_status"],
            "minimum_in_scope_recall": gate_policy["algorithm"][
                "minimum_in_scope_recall"
            ],
            "threshold": gate_policy["threshold"],
        },
        "online_model_called": False,
        "embedding_model_called": False,
    }
