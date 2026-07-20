from pydantic import BaseModel, Field, field_validator


class VectorSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=8_000)
    top_k: int = Field(default=5, ge=1, le=20)

    @field_validator("query", mode="before")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("query cannot be blank")
        return normalized


class VectorSearchResult(BaseModel):
    chunk_id: int
    document_id: int
    kb_id: int
    chunk_index: int
    content: str
    score: float


class VectorSearchResponse(BaseModel):
    query: str
    results: list[VectorSearchResult]
