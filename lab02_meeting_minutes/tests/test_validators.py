from lab02_meeting_minutes.src.schemas import ActionItem, Attendee, MeetingExtractionResult, ProcessingMetadata
from lab02_meeting_minutes.src.validators import evidence_exists, extract_speaker_names, validate_result_against_text


def test_extract_speaker_names_supports_colon_lines() -> None:
    text = "王芳：安排任务。\n[李明] 完成接口。\n张琳 - 复核标签。"
    assert extract_speaker_names(text) == {"王芳", "李明", "张琳"}


def test_extract_speaker_names_ignores_metadata_labels() -> None:
    text = "会议标题：测试会\n会议日期：2026-07-20\n王芳：安排任务。"
    assert extract_speaker_names(text) == {"王芳"}


def test_extract_speaker_names_supports_space_separated_qmsum_labels() -> None:
    text = "- Professor B: What do you think?\n- PhD D: I will run the experiment.\n- Grad A: Working on quals."
    assert extract_speaker_names(text) == {"Professor B", "PhD D", "Grad A"}


def test_evidence_exists_ignores_whitespace() -> None:
    text = "王芳：李明在下周三前完成退款接口异常码映射。"
    evidence = "李明在下周三前完成 退款接口异常码映射。"
    assert evidence_exists(text, evidence)


def test_evidence_exists_tolerates_transcript_noise_tokens() -> None:
    text = "- Project Manager: We have to use {vocalsound} the pen and the eraser ."
    evidence = "We have to use the pen and the eraser ."
    assert evidence_exists(text, evidence)


def test_evidence_exists_still_rejects_unanchored_text() -> None:
    text = "- Project Manager: We have to use {vocalsound} the pen and the eraser ."
    evidence = "We decided to use a touchscreen interface ."
    assert not evidence_exists(text, evidence)


def test_validate_owner_not_in_evidence() -> None:
    source = "王芳：李明在下周三前完成接口联调。"
    result = MeetingExtractionResult(
        meeting_id="m1",
        meeting_title="测试会",
        attendees=[Attendee(name="李明", evidence="王芳：李明在下周三前完成接口联调。")],
        topics=[],
        decisions=[],
        action_items=[ActionItem(action_id="A001", task="完成接口联调", owner="张琳", due_date_raw="下周三前", due_date_normalized="2026-07-29", evidence="李明在下周三前完成接口联调。")],
        open_questions=[],
        meeting_summary="摘要",
        processing_metadata=ProcessingMetadata(mode="single_pass", chunk_count=1, model="mock", prompt_version="prompt_v3_evidence_decision_guard_h3_draft", schema_version="schema_v1_h3_draft", validator_version="validator_v1_h3_draft"),
    )
    report = validate_result_against_text(result, source)
    assert not report.ok
    assert any(issue.code == "owner_not_in_speakers" for issue in report.issues)
