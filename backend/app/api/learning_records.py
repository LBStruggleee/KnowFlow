import json
from typing import Any

from app.core.database import get_db
from app.core.db_utils import safe_commit
from app.models.conversation import ChatMessage, Conversation
from app.models.knowledge_base import KnowledgeBase
from app.models.learning_record import LearningRecord
from app.schemas.learning_record import (
    LearningRecordCreate,
    LearningRecordRead,
    LearningRecordUpdate,
)
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/learning-records", tags=["learning records"])


@router.post("", response_model=LearningRecordRead, status_code=status.HTTP_201_CREATED)
def create_learning_record(
    payload: LearningRecordCreate,
    db: Session = Depends(get_db),
) -> LearningRecordRead:
    _validate_links(db, payload.kb_id, payload.conversation_id, payload.source_message_id)
    record = LearningRecord(
        kb_id=payload.kb_id,
        conversation_id=payload.conversation_id,
        source_message_id=payload.source_message_id,
        record_type=payload.record_type,
        title=payload.title,
        content=payload.content,
        tags_json=json.dumps(payload.tags, ensure_ascii=False),
        metadata_json=json.dumps(payload.metadata, ensure_ascii=False),
    )
    db.add(record)
    safe_commit(db)
    db.refresh(record)
    return _record_read(record)


@router.get("", response_model=list[LearningRecordRead])
def list_learning_records(
    kb_id: int | None = None,
    record_type: str | None = None,
    db: Session = Depends(get_db),
) -> list[LearningRecordRead]:
    statement = select(LearningRecord).order_by(LearningRecord.updated_at.desc())
    if kb_id is not None:
        statement = statement.where(LearningRecord.kb_id == kb_id)
    if record_type is not None:
        if record_type not in {"note", "exercise", "mistake"}:
            raise HTTPException(status_code=422, detail="Unsupported learning record type.")
        statement = statement.where(LearningRecord.record_type == record_type)
    return [_record_read(record) for record in db.scalars(statement)]


@router.get("/{record_id}", response_model=LearningRecordRead)
def get_learning_record(
    record_id: int,
    db: Session = Depends(get_db),
) -> LearningRecordRead:
    return _record_read(_get_record_or_404(db, record_id))


@router.patch("/{record_id}", response_model=LearningRecordRead)
def update_learning_record(
    record_id: int,
    payload: LearningRecordUpdate,
    db: Session = Depends(get_db),
) -> LearningRecordRead:
    record = _get_record_or_404(db, record_id)
    changes = payload.model_dump(exclude_unset=True)
    for field in ("record_type", "title", "content"):
        if field in changes:
            setattr(record, field, changes[field])
    if "tags" in changes:
        record.tags_json = json.dumps(changes["tags"], ensure_ascii=False)
    if "metadata" in changes:
        record.metadata_json = json.dumps(changes["metadata"], ensure_ascii=False)
    safe_commit(db)
    db.refresh(record)
    return _record_read(record)


@router.delete("/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_learning_record(
    record_id: int,
    db: Session = Depends(get_db),
) -> None:
    db.delete(_get_record_or_404(db, record_id))
    safe_commit(db)


def _validate_links(
    db: Session,
    kb_id: int,
    conversation_id: int | None,
    source_message_id: int | None,
) -> None:
    if db.get(KnowledgeBase, kb_id) is None:
        raise HTTPException(status_code=404, detail="Knowledge base not found.")
    if conversation_id is not None:
        conversation = db.get(Conversation, conversation_id)
        if conversation is None or conversation.kb_id != kb_id:
            raise HTTPException(status_code=404, detail="Conversation not found.")
    if source_message_id is not None:
        message = db.get(ChatMessage, source_message_id)
        if message is None or message.kb_id != kb_id:
            raise HTTPException(status_code=404, detail="Source message not found.")


def _get_record_or_404(db: Session, record_id: int) -> LearningRecord:
    record = db.get(LearningRecord, record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Learning record not found.")
    return record


def _load_json(value: str, default: Any) -> Any:
    try:
        loaded = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default
    return loaded if isinstance(loaded, type(default)) else default


def _record_read(record: LearningRecord) -> LearningRecordRead:
    return LearningRecordRead(
        id=record.id,
        kb_id=record.kb_id,
        conversation_id=record.conversation_id,
        source_message_id=record.source_message_id,
        record_type=record.record_type,
        title=record.title,
        content=record.content,
        tags=_load_json(record.tags_json, []),
        metadata=_load_json(record.metadata_json, {}),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )
