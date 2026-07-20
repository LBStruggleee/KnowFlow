from app.core.database import get_db
from app.models.conversation import ChatMessage, Conversation
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.knowledge_base import KnowledgeBase
from app.schemas.admin import (
    SystemSettingsRead,
    SystemSettingsUpdate,
    SystemStatusRead,
    TokenUsageRead,
)
from app.services.settings_service import typed_settings, update_settings
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/settings", response_model=SystemSettingsRead)
def get_system_settings(db: Session = Depends(get_db)) -> SystemSettingsRead:
    return SystemSettingsRead(**typed_settings(db))


@router.patch("/settings", response_model=SystemSettingsRead)
def patch_system_settings(
    payload: SystemSettingsUpdate,
    db: Session = Depends(get_db),
) -> SystemSettingsRead:
    values = update_settings(db, payload.model_dump(exclude_unset=True))
    return SystemSettingsRead(
        top_k=int(values["top_k"]),
        score_threshold=float(values["score_threshold"]),
        qwen_model=values["qwen_model"],
        temperature=float(values["temperature"]),
    )


@router.get("/status", response_model=SystemStatusRead)
def get_system_status(db: Session = Depends(get_db)) -> SystemStatusRead:
    token_usage = db.query(
        func.coalesce(func.sum(ChatMessage.prompt_tokens), 0),
        func.coalesce(func.sum(ChatMessage.completion_tokens), 0),
        func.coalesce(func.sum(ChatMessage.total_tokens), 0),
    ).one()
    return SystemStatusRead(
        knowledge_bases=db.query(KnowledgeBase).count(),
        documents=db.query(Document).count(),
        chunks=db.query(DocumentChunk).count(),
        conversations=db.query(Conversation).count(),
        messages=db.query(ChatMessage).count(),
        finished_documents=db.query(Document).filter(Document.status == "finished").count(),
        failed_documents=db.query(Document).filter(Document.status == "failed").count(),
        token_usage=TokenUsageRead(
            prompt_tokens=int(token_usage[0] or 0),
            completion_tokens=int(token_usage[1] or 0),
            total_tokens=int(token_usage[2] or 0),
        ),
    )
