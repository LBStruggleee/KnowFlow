from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ConversationCreate(BaseModel):
    kb_id: int
    title: str = Field(default="新会话", max_length=200)


class ConversationRead(BaseModel):
    id: int
    kb_id: int
    title: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


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
