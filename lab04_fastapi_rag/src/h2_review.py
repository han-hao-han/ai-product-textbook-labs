from __future__ import annotations

from typing import Any

from .h2_questions import H2Question, H2QuestionSet


SCOPE_LABELS = {
    "in_scope": "知识库内",
    "boundary": "边界",
    "out_of_scope": "知识库外",
}


def _question_lines(item: H2Question) -> list[str]:
    sources = [
        path
        for group in item.acceptable_source_groups
        for path in group.paths
    ]
    lines = [
        f"### {item.question_id}｜{SCOPE_LABELS[item.scope]}",
        "",
        f"- 问题：{item.question}",
        f"- 预期行为：{item.expected_behavior}",
        f"- 题型：{item.question_type}",
        f"- 文档组：{item.document_group or '不适用'}",
        f"- 要求短Python代码：{item.contains_short_python_code}",
        "- 必答点：",
        *[f"  - {point}" for point in item.required_points],
        "- 可选点：",
        *(
            [f"  - {point}" for point in item.optional_points]
            if item.optional_points
            else ["  - 无"]
        ),
        "- 关键错误：",
        *[f"  - {error}" for error in item.critical_errors],
        "- 可接受来源：",
        *([f"  - `{path}`" for path in sources] if sources else ["  - 无"]),
    ]
    if item.related_corpus_paths:
        lines.extend(
            [
                "- 相关但不足以作答的语料：",
                *[f"  - `{path}`" for path in item.related_corpus_paths],
            ]
        )
    lines.append("")
    return lines


def render_h2_candidate_review(
    calibration: H2QuestionSet,
    evaluation: H2QuestionSet,
    gate_policy: dict[str, Any],
    audit: dict[str, Any],
) -> str:
    lines = [
        "# H2题集与门控算法候选审阅",
        "",
        "## 状态",
        "",
        "```text",
        "candidate_pending_h2_confirmation",
        "```",
        "",
        "本文件只展示人工编制候选，不包含任何检索分数。确认H2前不得运行阈值计算。",
        "",
        "## 冻结依据",
        "",
        f"- FastAPI Commit：`{audit['source_commit']}`",
        f"- 语料SHA-256：`{audit['corpus_sha256']}`",
        f"- 校准集SHA-256：`{audit['calibration']['sha256']}`",
        f"- 正式集SHA-256：`{audit['evaluation']['sha256']}`",
        "",
        "## 配额审计",
        "",
        f"- 校准集：{audit['calibration']['scope_counts']}",
        f"- 正式集：{audit['evaluation']['scope_counts']}",
        f"- 正式文档组：{audit['evaluation']['document_group_counts']}",
        f"- 正式题型：{audit['evaluation']['question_type_counts']}",
        "- 正式短Python代码题："
        f"{audit['evaluation']['questions_with_short_python_code']}",
        "",
        "## 门控算法候选",
        "",
        "- 分数：Top 1精确余弦相似度；",
        "- 通过规则：`top1_score >= threshold`；",
        "- 正类：20道知识库内题；",
        "- 负类：10道边界题与20道知识库外题；",
        "- 约束：知识库内召回率至少90%；",
        "- 主目标：满足召回约束时，最大化负类拒绝率；",
        "- 阈值只从相邻唯一校准分数的中点和外侧边界中选择；",
        "- 正式集分数在阈值冻结前不可见，正式结果不得用于回调阈值。",
        "",
        "算法原始配置：",
        "",
        "```text",
        str(gate_policy["algorithm"]),
        "```",
        "",
        "## 校准集（50题）",
        "",
    ]
    for item in calibration.questions:
        lines.extend(_question_lines(item))
    lines.extend(["## 正式验证集（30题）", ""])
    for item in evaluation.questions:
        lines.extend(_question_lines(item))
    lines.extend(
        [
            "## 人工确认提示",
            "",
            "请重点检查：问题是否自然、范围标签是否合理、必答点是否确有来源、"
            "关键错误是否足够保守，以及边界题是否确实无法由冻结语料充分回答。",
            "",
        ]
    )
    return "\n".join(lines)
