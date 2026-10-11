import logging
import shutil
import threading
from pathlib import Path

from app.core.database import get_db
from app.core.db_utils import commit_or_conflict, get_knowledge_base_or_404, safe_commit
from app.core.files import UPLOAD_ROOT, safe_unlink
from app.models.conversation import ChatMessage, Conversation
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.document_section import DocumentSection
from app.models.knowledge_base import KnowledgeBase
from app.models.learning_record import LearningRecord
from app.schemas.knowledge_base import (
    IndexRebuildRead,
    KnowledgeBaseCreate,
    KnowledgeBaseRead,
    KnowledgeBaseUpdate,
)
from app.services.document_processing_service import (
    process_document_record,
    reset_document_for_retry,
)
from app.services.vector_store_service import vector_store_service
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/kbs", tags=["knowledge bases"])
logger = logging.getLogger(__name__)

# In-process guard so two rebuild requests for the same knowledge base can
# never overlap. The synchronous long request is kept deliberately (see the
# endpoint comment); the guard removes the concurrent-write window.
_rebuild_guard = threading.Lock()
_rebuilding_kbs: set[int] = set()


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
    commit_or_conflict(db)
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
    return get_knowledge_base_or_404(db, kb_id)


@router.patch("/{kb_id}", response_model=KnowledgeBaseRead)
def update_knowledge_base(
    kb_id: int,
    payload: KnowledgeBaseUpdate,
    db: Session = Depends(get_db),
) -> KnowledgeBase:
    knowledge_base = get_knowledge_base_or_404(db, kb_id)

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

    commit_or_conflict(db)
    db.refresh(knowledge_base)
    return knowledge_base


@router.delete("/{kb_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_knowledge_base(
    kb_id: int,
    db: Session = Depends(get_db),
) -> None:
    knowledge_base = get_knowledge_base_or_404(db, kb_id)
    documents = list(db.scalars(select(Document).where(Document.kb_id == kb_id)))
    file_paths = [Path(document.file_path) for document in documents]

    db.query(ChatMessage).filter(ChatMessage.kb_id == kb_id).delete()
    db.query(LearningRecord).filter(LearningRecord.kb_id == kb_id).delete()
    db.query(Conversation).filter(Conversation.kb_id == kb_id).delete()
    db.query(DocumentChunk).filter(DocumentChunk.kb_id == kb_id).delete()
    db.query(DocumentSection).filter(
        DocumentSection.document_id.in_(select(Document.id).where(Document.kb_id == kb_id))
    ).delete(synchronize_session=False)
    db.query(Document).filter(Document.kb_id == kb_id).delete()
    db.delete(knowledge_base)
    safe_commit(db)

    try:
        vector_store_service.delete_knowledge_base(kb_id)
    except Exception:
        logger.exception("Vector cleanup failed for deleted knowledge base id=%s", kb_id)
    for file_path in file_paths:
        safe_unlink(file_path)
    _remove_upload_dir(kb_id)


@router.post("/{kb_id}/rebuild-index", response_model=IndexRebuildRead)
def rebuild_knowledge_base_index(
    kb_id: int,
    db: Session = Depends(get_db),
) -> IndexRebuildRead:
    # Kept synchronous on purpose: the single-user deployment has no polling
    # UI, so async rebuilds would need new status plumbing. The guard below
    # and the processing check make concurrent invocations fail fast instead
    # of interleaving vector writes.
    with _rebuild_guard:
        if kb_id in _rebuilding_kbs:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Index rebuild is already running for this knowledge base.",
            )
        _rebuilding_kbs.add(kb_id)
    try:
        return _rebuild_index(db, kb_id)
    finally:
        with _rebuild_guard:
            _rebuilding_kbs.discard(kb_id)


def _rebuild_index(db: Session, kb_id: int) -> IndexRebuildRead:
    get_knowledge_base_or_404(db, kb_id)
    processing_id = db.scalar(
        select(Document.id).where(Document.kb_id == kb_id, Document.status == "processing").limit(1)
    )
    if processing_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Knowledge base has documents still processing. Retry after they finish.",
        )

    documents = list(
        db.scalars(
            select(Document)
            .where(Document.kb_id == kb_id, Document.status == "finished")
            .order_by(Document.id)
        )
    )
    try:
        indexed_chunks = 0
        for document in documents:
            if Path(document.file_path).is_file():
                reset_document_for_retry(db, document)
                process_document_record(db, document.id)
                finished = db.get(Document, document.id)
                if finished is not None and finished.status == "finished":
                    indexed_chunks += (
                        db.scalar(
                            select(func.count(DocumentChunk.id)).where(
                                DocumentChunk.document_id == document.id
                            )
                        )
                        or 0
                    )
            else:
                indexed_chunks += _reindex_chunks_without_source(db, kb_id, document)
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
        indexed_chunks=indexed_chunks,
        collection=vector_store_service.collection_name,
        embedding_provider=vector_store_service.embedding_provider,
    )


def _reindex_chunks_without_source(db: Session, kb_id: int, document: Document) -> int:
    """Refresh vectors for chunks whose source file is gone.

    Vectors are deleted first, so a failed re-index would lose them; the
    compensation below re-runs the upsert once and turns a persistent
    failure into an explicit 502 instead of silent data loss.
    """
    stale = list(db.scalars(select(DocumentChunk).where(DocumentChunk.document_id == document.id)))
    stale_paths = _chunk_section_paths(db, stale)
    vector_store_service.delete_chunks([chunk.id for chunk in stale])
    try:
        vector_store_service.add_chunks(stale, stale_paths)
    except Exception as exc:
        logger.exception(
            "Re-indexing %s chunks without source files failed for knowledge base id=%s",
            len(stale),
            kb_id,
        )
        try:
            vector_store_service.add_chunks(stale, stale_paths)
        except Exception:
            logger.exception(
                "Vector compensation failed for knowledge base id=%s; "
                "run rebuild again to restore these vectors",
                kb_id,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=(
                    "Could not rebuild the vector index. "
                    "Run rebuild again to restore missing vectors."
                ),
            ) from exc
        logger.warning("Vector compensation succeeded for knowledge base id=%s", kb_id)
    return len(stale)


def _chunk_section_paths(db: Session, chunks: list[DocumentChunk]) -> dict[int, str]:
    section_ids = {chunk.section_id for chunk in chunks if chunk.section_id is not None}
    if not section_ids:
        return {}
    by_section = dict(
        db.execute(
            select(DocumentSection.id, DocumentSection.section_path).where(
                DocumentSection.id.in_(section_ids)
            )
        ).all()
    )
    return {
        chunk.id: by_section.get(chunk.section_id, "")
        for chunk in chunks
        if chunk.id is not None and chunk.section_id is not None
    }


def _remove_upload_dir(kb_id: int) -> None:
    upload_dir = UPLOAD_ROOT / str(kb_id)
    if upload_dir.is_dir():
        shutil.rmtree(upload_dir, ignore_errors=True)
