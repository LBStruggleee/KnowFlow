from typing import Any

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    kb_id: int
    question: str = Field(min_length=1, max_length=8_000)
    top_k: int | None = Field(default=None, ge=1, le=20)
    conversation_id: int | None = None

    @field_validator("question", mode="before")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("question cannot be blank")
        return normalized


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
