from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class KnowledgeBaseFields(BaseModel):
    @field_validator("name", "description", "category", check_fields=False, mode="before")
    @classmethod
    def normalize_text_fields(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


class KnowledgeBaseCreate(KnowledgeBaseFields):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    category: str = Field(default="", max_length=100)


class KnowledgeBaseUpdate(KnowledgeBaseFields):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    category: str | None = Field(default=None, max_length=100)


class KnowledgeBaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    category: str
    created_at: datetime
    updated_at: datetime


class IndexRebuildRead(BaseModel):
    kb_id: int
    indexed_chunks: int
    collection: str
    embedding_provider: str
