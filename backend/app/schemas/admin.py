from pydantic import BaseModel, Field


class SystemSettingsRead(BaseModel):
    top_k: int
    score_threshold: float
    qwen_model: str
    temperature: float


class SystemSettingsUpdate(BaseModel):
    top_k: int | None = Field(default=None, ge=1, le=20)
    score_threshold: float | None = Field(default=None, ge=0, le=1)
    qwen_model: str | None = Field(default=None, min_length=1, max_length=100)
    temperature: float | None = Field(default=None, ge=0, le=2)


class TokenUsageRead(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class SystemStatusRead(BaseModel):
    knowledge_bases: int
    documents: int
    chunks: int
    conversations: int
    messages: int
    finished_documents: int
    failed_documents: int
    token_usage: TokenUsageRead
