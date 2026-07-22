import pytest
from pydantic import ValidationError

from lab02_meeting_minutes.src.schemas import ActionItem, MeetingExtractionResult, ProcessingMetadata


def test_action_owner_empty_list_is_invalid() -> None:
    with pytest.raises(ValidationError):
        ActionItem(action_id="A001", task="处理问题", owner=[], evidence="王芳：处理问题。")


def test_meeting_result_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        MeetingExtractionResult(
            meeting_id="m1",
            meeting_title="测试会",
            attendees=[],
            topics=[],
            decisions=[],
            action_items=[],
            open_questions=[],
            meeting_summary="摘要",
            processing_metadata=ProcessingMetadata(
                mode="single_pass",
                chunk_count=1,
                model="mock",
                prompt_version="prompt_v3_evidence_decision_guard_h3_draft",
                schema_version="schema_v1_h3_draft",
                validator_version="validator_v1_h3_draft",
            ),
            unexpected=True,
        )
