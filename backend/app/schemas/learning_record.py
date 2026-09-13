from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

LearningRecordType = Literal["note", "exercise", "mistake"]


class LearningRecordCreate(BaseModel):
    kb_id: int
    conversation_id: int | None = None
    source_message_id: int | None = None
    record_type: LearningRecordType
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=50_000)
    tags: list[str] = Field(default_factory=list, max_length=20)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("title", "content", mode="before")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value cannot be blank")
        return normalized

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(tag.strip()[:50] for tag in value if tag.strip()))


class LearningRecordUpdate(BaseModel):
    record_type: LearningRecordType | None = None
    title: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = Field(default=None, min_length=1, max_length=50_000)
    tags: list[str] | None = Field(default=None, max_length=20)
    metadata: dict[str, Any] | None = None

    @field_validator("title", "content", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("value cannot be blank")
        return normalized

    @field_validator("tags")
    @classmethod
    def normalize_optional_tags(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return list(dict.fromkeys(tag.strip()[:50] for tag in value if tag.strip()))


class LearningRecordRead(BaseModel):
    id: int
    kb_id: int
    conversation_id: int | None
    source_message_id: int | None
    record_type: LearningRecordType
    title: str
    content: str
    tags: list[str]
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime
