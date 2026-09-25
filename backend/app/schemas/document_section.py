from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentSectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    parent_section_id: int | None
    title: str
    section_path: str
    section_level: int
    section_order: int
    chunk_count: int
    created_at: datetime


class DocumentSectionTree(DocumentSectionRead):
    children: list["DocumentSectionTree"] = []


DocumentSectionTree.model_rebuild()
