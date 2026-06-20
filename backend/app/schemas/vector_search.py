from pydantic import BaseModel, Field


class VectorSearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)


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
