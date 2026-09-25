from typing import Literal

from pydantic import BaseModel, Field


class SystemSettingsRead(BaseModel):
    top_k: int
    score_threshold: float
    qwen_model: str
    temperature: float
    privacy_mode: Literal["local", "hybrid", "cloud"]
    glass_variant: Literal["clear", "balanced", "contrast"]
    retrieval_channels: Literal["vector", "lexical", "hybrid"]


class SystemSettingsUpdate(BaseModel):
    top_k: int | None = Field(default=None, ge=1, le=20)
    score_threshold: float | None = Field(default=None, ge=0, le=1)
    qwen_model: str | None = Field(default=None, min_length=1, max_length=100)
    temperature: float | None = Field(default=None, ge=0, le=2)
    privacy_mode: Literal["local", "hybrid", "cloud"] | None = None
    glass_variant: Literal["clear", "balanced", "contrast"] | None = None
    # Plain str (not Literal) so unknown values reach normalization
    # instead of 422; update_settings coerces them to "hybrid".
    retrieval_channels: str | None = Field(default=None)


class ProviderStatusRead(BaseModel):
    llm_provider: str
    llm_available: bool
    embedding_provider: str
    vector_collection: str
    privacy_mode: Literal["local", "hybrid", "cloud"]


class DataClearRead(BaseModel):
    knowledge_bases: int
    documents: int
    conversations: int
    learning_records: int


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
