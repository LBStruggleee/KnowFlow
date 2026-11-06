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
    section_id: int | None = None
    section_path: str = ""
    # Whether the ingestion-time screen flagged this chunk, and which rules
    # fired. Additive fields: older clients simply ignore them.
    injection_flag: bool = False
    injection_rules: list[str] = []
    injection_score: float = 0.0
