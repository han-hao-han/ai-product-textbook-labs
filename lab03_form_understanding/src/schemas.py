from __future__ import annotations

from pydantic import BaseModel, ConfigDict, StrictStr


PROMPT_VERSION = "v1"
SCHEMA_VERSION = "v1"


class ExtractedField(BaseModel):
    """One key-value relation returned by the vision model."""

    model_config = ConfigDict(extra="forbid", strict=True)

    key: StrictStr
    value: StrictStr


class FormExtractionResult(BaseModel):
    """The complete model-owned output; evaluation fields are forbidden."""

    model_config = ConfigDict(extra="forbid", strict=True)

    fields: list[ExtractedField]
    warnings: list[StrictStr]
