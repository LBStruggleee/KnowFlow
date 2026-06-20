from pathlib import Path
import shutil

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.knowledge_base import KnowledgeBase
from app.schemas.knowledge_base import (
    KnowledgeBaseCreate,
    KnowledgeBaseRead,
    KnowledgeBaseUpdate,
)
from app.services.vector_store_service import vector_store_service

router = APIRouter(prefix="/api/kbs", tags=["knowledge bases"])


@router.post(
    "",
    response_model=KnowledgeBaseRead,
    status_code=status.HTTP_201_CREATED,
)
def create_knowledge_base(
    payload: KnowledgeBaseCreate,
    db: Session = Depends(get_db),
) -> KnowledgeBase:
    existing = db.scalar(
        select(KnowledgeBase).where(KnowledgeBase.name == payload.name)
    )
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
    db.commit()
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
    knowledge_base = db.get(KnowledgeBase, kb_id)
    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found.",
        )
    return knowledge_base


@router.patch("/{kb_id}", response_model=KnowledgeBaseRead)
def update_knowledge_base(
    kb_id: int,
    payload: KnowledgeBaseUpdate,
    db: Session = Depends(get_db),
) -> KnowledgeBase:
    knowledge_base = db.get(KnowledgeBase, kb_id)
    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found.",
        )

    if payload.name is not None and payload.name != knowledge_base.name:
        existing = db.scalar(
            select(KnowledgeBase).where(KnowledgeBase.name == payload.name)
        )
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

    db.commit()
    db.refresh(knowledge_base)
    return knowledge_base


@router.delete("/{kb_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_knowledge_base(
    kb_id: int,
    db: Session = Depends(get_db),
) -> None:
    knowledge_base = db.get(KnowledgeBase, kb_id)
    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found.",
        )

    documents = list(db.scalars(select(Document).where(Document.kb_id == kb_id)))
    vector_store_service.delete_knowledge_base(kb_id)

    for document in documents:
        file_path = Path(document.file_path)
        if file_path.exists():
            file_path.unlink()

    db.query(DocumentChunk).filter(DocumentChunk.kb_id == kb_id).delete()
    db.query(Document).filter(Document.kb_id == kb_id).delete()
    db.delete(knowledge_base)
    db.commit()

    if documents:
        upload_dir = Path(documents[0].file_path).parent
        if upload_dir.exists() and upload_dir.name == str(kb_id):
            shutil.rmtree(upload_dir, ignore_errors=True)
