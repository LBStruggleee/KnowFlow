from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kb_id: int
    title: str
    file_name: str
    file_type: str
    status: str
    content_length: int
    content_preview: str
    error_message: str
    chunk_count: int = 0
    created_at: datetime
    updated_at: datetime
