from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProcessingMode(str, Enum):
    single_pass = "single_pass"
    chunked = "chunked"


class ActionStatus(str, Enum):
    pending = "pending"
    done = "done"
    blocked = "blocked"
    unknown = "unknown"


class Attendee(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    role: str | None = None
    evidence: str


class Topic(BaseModel):
    model_config = ConfigDict(extra="forbid")
    topic_id: str
    topic: str
    evidence: str


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision_id: str
    decision: str
    evidence: str


class ActionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_id: str
    task: str
    owner: str | list[str] | None = None
    due_date_raw: str | None = None
    due_date_normalized: str | None = None
    status: ActionStatus = ActionStatus.pending
    evidence: str

    @field_validator("owner")
    @classmethod
    def owner_list_must_not_be_empty(cls, value: str | list[str] | None) -> str | list[str] | None:
        if isinstance(value, list) and not value:
            raise ValueError("owner list must not be empty; use null when owner is not mentioned")
        return value


class OpenQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_id: str
    question: str
    owner: str | None = None
    evidence: str


class ValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    message: str
    item_id: str | None = None
    severity: Literal["error", "warning"] = "error"


class ProcessingMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: ProcessingMode
    chunk_count: int = Field(ge=1)
    model: str
    prompt_version: str
    schema_version: str
    validator_version: str
    elapsed_seconds: float | None = Field(default=None, ge=0)
    usage: dict[str, Any] = Field(default_factory=dict)


class MeetingExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    meeting_id: str
    meeting_title: str
    meeting_date: str | None = None
    attendees: list[Attendee]
    topics: list[Topic]
    decisions: list[Decision]
    action_items: list[ActionItem]
    open_questions: list[OpenQuestion]
    meeting_summary: str
    processing_metadata: ProcessingMetadata
    validation_issues: list[ValidationIssue] = Field(default_factory=list)


SCHEMA_VERSION = "schema_v1_h3_draft"
