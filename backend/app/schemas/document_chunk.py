from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentChunkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kb_id: int
    document_id: int
    chunk_index: int
    content: str
    token_count: int
    created_at: datetime
