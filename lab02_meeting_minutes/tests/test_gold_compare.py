from lab02_meeting_minutes.src.gold_compare import compare_case_gold, compare_main_gold


def test_compare_main_gold_passes_matching_items() -> None:
    gold = {
        "action_items": [
            {"action_id": "A001", "task": "准备客服培训说明", "owner": None, "due_date_normalized": None, "evidence": "准备客服培训说明"}
        ],
        "decisions": [{"decision_id": "D001", "decision": "只覆盖 Web 工作台", "evidence": "MVP 首版只覆盖 Web 客服工作台"}],
        "open_questions": [{"question_id": "Q001", "question": "客服培训说明由谁负责", "evidence": "明确谁负责"}],
    }
    result = {
        "action_items": [
            {"action_id": "A001", "task": "准备客服培训说明", "owner": None, "due_date_normalized": None, "evidence": "准备客服培训说明"}
        ],
        "decisions": [{"decision_id": "D001", "decision": "MVP 首版只覆盖 Web 客服工作台", "evidence": "MVP 首版只覆盖 Web 客服工作台"}],
        "open_questions": [{"question_id": "Q001", "question": "灰度前客服培训说明由谁负责", "evidence": "明确谁负责"}],
    }

    report = compare_main_gold(gold, result)

    assert report.ok
    assert report.issues == []


def test_compare_main_gold_reports_missing_and_unexpected_items() -> None:
    gold = {
        "action_items": [
            {"action_id": "A001", "task": "准备客服培训说明", "owner": None, "due_date_normalized": None, "evidence": "准备客服培训说明"}
        ],
        "decisions": [{"decision_id": "D001", "decision": "前端风险提示按二次确认方案实现", "evidence": "前端先按二次确认方案实现。"}],
        "open_questions": [{"question_id": "Q001", "question": "客服培训说明由谁负责", "evidence": "明确谁负责"}],
    }
    result = {
        "action_items": [],
        "decisions": [{"decision_id": "D999", "decision": "李明下周三前完成联调", "evidence": "李明在下周三前完成退款接口异常码映射和联调验证。"}],
        "open_questions": [],
    }

    report = compare_main_gold(gold, result)

    assert not report.ok
    assert {(issue.kind, issue.code, issue.gold_id, issue.result_id) for issue in report.issues} == {
        ("action_items", "missing_gold_item", "A001", None),
        ("decisions", "missing_gold_item", "D001", None),
        ("decisions", "unexpected_result_item", None, "D999"),
        ("open_questions", "missing_gold_item", "Q001", None),
    }


def test_compare_main_gold_matches_close_question_wording() -> None:
    gold = {
        "action_items": [],
        "decisions": [],
        "open_questions": [
            {
                "question_id": "Q001",
                "question": "上线首版是否需要接入人工转接原因字段以支持满意度标签分析",
                "evidence": "需要确认上线首版是否真的要接入人工转接原因",
            }
        ],
    }
    result = {
        "action_items": [],
        "decisions": [],
        "open_questions": [
            {
                "question_id": "Q777",
                "question": "是否要接入人工转接原因字段用于满意度标签分析",
                "evidence": "满意度标签这件事先不做决策。",
            }
        ],
    }

    report = compare_main_gold(gold, result)

    assert report.ok


def test_compare_main_gold_matches_reordered_question_wording() -> None:
    gold = {
        "action_items": [],
        "decisions": [],
        "open_questions": [
            {
                "question_id": "Q003",
                "question": "灰度上线前客服培训说明由谁负责",
                "evidence": "下一次项目会上明确谁负责。",
            }
        ],
    }
    result = {
        "action_items": [],
        "decisions": [],
        "open_questions": [
            {
                "question_id": "Q003",
                "question": "谁来负责准备客服培训说明？",
                "evidence": "下一次项目会上明确谁负责。",
            }
        ],
    }

    report = compare_main_gold(gold, result)

    assert report.ok


def test_compare_case_gold_uses_result_meeting_id() -> None:
    gold = {
        "cases": [
            {
                "meeting_id": "demo_001",
                "expected_action_items": [
                    {"task": "更新评测样例", "owner": "何佳", "due_date_normalized": "2026-07-27", "evidence": "何佳在下周一前更新评测样例。"}
                ],
                "expected_decisions": [],
                "expected_open_questions": [],
            }
        ]
    }
    result = {
        "meeting_id": "demo_001",
        "action_items": [
            {"action_id": "A001", "task": "更新评测样例", "owner": "何佳", "due_date_normalized": "2026-07-27", "evidence": "何佳在下周一前更新评测样例。"}
        ],
        "decisions": [],
        "open_questions": [],
    }

    report = compare_case_gold(gold, result)

    assert report.ok
