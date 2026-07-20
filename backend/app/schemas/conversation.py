from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ConversationCreate(BaseModel):
    kb_id: int
    title: str = Field(default="新会话", min_length=1, max_length=200)

    @field_validator("title", mode="before")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("title cannot be blank")
        return normalized


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kb_id: int
    title: str
    created_at: datetime
    updated_at: datetime


class ChatMessageRead(BaseModel):
    id: int
    conversation_id: int
    kb_id: int
    role: str
    content: str
    sources: list[dict[str, Any]]
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    created_at: datetime


class ConversationDetail(ConversationRead):
    messages: list[ChatMessageRead]
