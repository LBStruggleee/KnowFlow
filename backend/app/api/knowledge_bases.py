import logging
import shutil
from pathlib import Path

from app.core.database import BASE_DIR, get_db
from app.models.conversation import ChatMessage, Conversation
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.knowledge_base import KnowledgeBase
from app.schemas.knowledge_base import (
    IndexRebuildRead,
    KnowledgeBaseCreate,
    KnowledgeBaseRead,
    KnowledgeBaseUpdate,
)
from app.services.vector_store_service import vector_store_service
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/kbs", tags=["knowledge bases"])
logger = logging.getLogger(__name__)
UPLOAD_ROOT = BASE_DIR / "storage" / "uploads"


@router.post(
    "",
    response_model=KnowledgeBaseRead,
    status_code=status.HTTP_201_CREATED,
)
def create_knowledge_base(
    payload: KnowledgeBaseCreate,
    db: Session = Depends(get_db),
) -> KnowledgeBase:
    existing = db.scalar(select(KnowledgeBase).where(KnowledgeBase.name == payload.name))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Knowledge base name already exists.",
        )

    knowledge_base = KnowledgeBase(
        name=payload.name,
        description=payload.description,
        category=payload.category,
    )
    db.add(knowledge_base)
    _commit_or_conflict(db)
    db.refresh(knowledge_base)
    return knowledge_base


@router.get("", response_model=list[KnowledgeBaseRead])
def list_knowledge_bases(db: Session = Depends(get_db)) -> list[KnowledgeBase]:
    return list(db.scalars(select(KnowledgeBase).order_by(KnowledgeBase.id.desc())))


@router.get("/{kb_id}", response_model=KnowledgeBaseRead)
def get_knowledge_base(
    kb_id: int,
    db: Session = Depends(get_db),
) -> KnowledgeBase:
    return _get_knowledge_base_or_404(db, kb_id)


@router.patch("/{kb_id}", response_model=KnowledgeBaseRead)
def update_knowledge_base(
    kb_id: int,
    payload: KnowledgeBaseUpdate,
    db: Session = Depends(get_db),
) -> KnowledgeBase:
    knowledge_base = _get_knowledge_base_or_404(db, kb_id)

    if payload.name is not None and payload.name != knowledge_base.name:
        existing = db.scalar(select(KnowledgeBase).where(KnowledgeBase.name == payload.name))
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Knowledge base name already exists.",
            )
        knowledge_base.name = payload.name

    if payload.description is not None:
        knowledge_base.description = payload.description
    if payload.category is not None:
        knowledge_base.category = payload.category

    _commit_or_conflict(db)
    db.refresh(knowledge_base)
    return knowledge_base


@router.delete("/{kb_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_knowledge_base(
    kb_id: int,
    db: Session = Depends(get_db),
) -> None:
    knowledge_base = _get_knowledge_base_or_404(db, kb_id)
    documents = list(db.scalars(select(Document).where(Document.kb_id == kb_id)))
    file_paths = [Path(document.file_path) for document in documents]

    db.query(ChatMessage).filter(ChatMessage.kb_id == kb_id).delete()
    db.query(Conversation).filter(Conversation.kb_id == kb_id).delete()
    db.query(DocumentChunk).filter(DocumentChunk.kb_id == kb_id).delete()
    db.query(Document).filter(Document.kb_id == kb_id).delete()
    db.delete(knowledge_base)
    db.commit()

    try:
        vector_store_service.delete_knowledge_base(kb_id)
    except Exception:
        logger.exception("Vector cleanup failed for deleted knowledge base id=%s", kb_id)
    for file_path in file_paths:
        _safe_unlink(file_path)
    _remove_upload_dir(kb_id)


@router.post("/{kb_id}/rebuild-index", response_model=IndexRebuildRead)
def rebuild_knowledge_base_index(
    kb_id: int,
    db: Session = Depends(get_db),
) -> IndexRebuildRead:
    _get_knowledge_base_or_404(db, kb_id)
    chunks = list(
        db.scalars(
            select(DocumentChunk).where(DocumentChunk.kb_id == kb_id).order_by(DocumentChunk.id)
        )
    )
    try:
        vector_store_service.delete_knowledge_base(kb_id)
        vector_store_service.add_chunks(chunks)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Index rebuild failed for knowledge base id=%s", kb_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not rebuild the vector index.",
        ) from exc
    return IndexRebuildRead(
        kb_id=kb_id,
        indexed_chunks=len(chunks),
        collection=vector_store_service.collection_name,
        embedding_provider=vector_store_service.embedding_provider,
    )


def _get_knowledge_base_or_404(db: Session, kb_id: int) -> KnowledgeBase:
    knowledge_base = db.get(KnowledgeBase, kb_id)
    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found.",
        )
    return knowledge_base


def _commit_or_conflict(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Knowledge base name already exists.",
        ) from exc


def _safe_unlink(file_path: Path) -> None:
    try:
        file_path.resolve().relative_to(UPLOAD_ROOT.resolve())
    except ValueError:
        logger.error("Refusing to delete path outside upload directory: %s", file_path)
        return
    try:
        file_path.unlink(missing_ok=True)
    except OSError:
        logger.exception("Could not delete uploaded file: %s", file_path)


def _remove_upload_dir(kb_id: int) -> None:
    upload_dir = UPLOAD_ROOT / str(kb_id)
    if upload_dir.is_dir():
        shutil.rmtree(upload_dir, ignore_errors=True)
