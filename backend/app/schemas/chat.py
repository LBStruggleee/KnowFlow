from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    kb_id: int
    question: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=10)
    conversation_id: int | None = None


class ChatSource(BaseModel):
    chunk_id: int
    document_id: int
    kb_id: int
    chunk_index: int
    content: str
    score: float


class ChatUsage(BaseModel):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class ChatResponse(BaseModel):
    conversation_id: int
    answer: str
    sources: list[ChatSource]
    usage: ChatUsage | dict[str, Any] | None = None
    retrieval_trace: dict[str, Any] | None = None
