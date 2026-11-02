from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SystemSettingsRead(BaseModel):
    top_k: int
    score_threshold: float
    qwen_model: str
    temperature: float
    privacy_mode: Literal["local", "hybrid", "cloud"]
    glass_variant: Literal["clear", "balanced", "contrast"]
    retrieval_channels: Literal["vector", "lexical", "hybrid"]


class SystemSettingsUpdate(BaseModel):
    # Unknown keys must fail validation (422) instead of being silently dropped.
    model_config = ConfigDict(extra="forbid")

    top_k: int | None = Field(default=None, ge=1, le=20)
    score_threshold: float | None = Field(default=None, ge=0, le=1)
    qwen_model: str | None = Field(default=None, min_length=1, max_length=100)
    temperature: float | None = Field(default=None, ge=0, le=2)
    privacy_mode: Literal["local", "hybrid", "cloud"] | None = None
    glass_variant: Literal["clear", "balanced", "contrast"] | None = None
    # Plain str (not Literal) so unknown values reach normalization
    # instead of 422; update_settings coerces them to "hybrid".
    retrieval_channels: str | None = Field(default=None)


class VectorIndexCollectionRead(BaseModel):
    index_name: str
    collection: str
    chunks: int


class VectorIndexStatusRead(BaseModel):
    """Visibility for the per-provider vector collections.

    ``index_stale`` means chunks exist in a non-active collection: those chunks
    are unreachable on the vector channel until the knowledge base is rebuilt.
    """

    active_index_name: str
    active_collection: str
    active_chunks: int
    stale_collections: list[VectorIndexCollectionRead]
    stale_chunks: int
    index_stale: bool


class ProviderStatusRead(BaseModel):
    llm_provider: str
    llm_available: bool
    embedding_provider: str
    embedding_mode: Literal["semantic", "hashing"]
    embedding_degraded: bool
    embedding_notice: str
    vector_collection: str
    vector_index: VectorIndexStatusRead
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
