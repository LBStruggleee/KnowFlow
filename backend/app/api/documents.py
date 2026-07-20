import logging
from pathlib import Path
from uuid import uuid4

from app.core.config import settings
from app.core.database import BASE_DIR, get_db
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.knowledge_base import KnowledgeBase
from app.schemas.document import DocumentRead
from app.schemas.document_chunk import DocumentChunkRead
from app.services.document_parser import SUPPORTED_FILE_TYPES, parse_document_text
from app.services.text_chunker import estimate_token_count, split_text
from app.services.vector_store_service import vector_store_service
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func, select
from sqlalchemy.orm import Session

router = APIRouter(tags=["documents"])

UPLOAD_DIR = BASE_DIR / "storage" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
logger = logging.getLogger(__name__)
READ_CHUNK_SIZE = 1024 * 1024


@router.post(
    "/api/kbs/{kb_id}/documents/upload",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    kb_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> DocumentRead:
    knowledge_base = db.get(KnowledgeBase, kb_id)
    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found.",
        )

    original_name = Path(file.filename or "uploaded_file").name
    suffix = Path(original_name).suffix.lower()
    if suffix not in SUPPORTED_FILE_TYPES:
        supported = ", ".join(sorted(SUPPORTED_FILE_TYPES))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type. Supported: {supported}",
        )

    kb_upload_dir = UPLOAD_DIR / str(kb_id)
    kb_upload_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid4().hex}{suffix}"
    stored_path = kb_upload_dir / stored_name

    bytes_written = 0
    try:
        with stored_path.open("wb") as destination:
            while content := await file.read(READ_CHUNK_SIZE):
                bytes_written += len(content)
                if bytes_written > settings.upload_max_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail=f"File exceeds the {settings.upload_max_bytes} byte upload limit.",
                    )
                destination.write(content)
    except Exception:
        stored_path.unlink(missing_ok=True)
        raise
    if bytes_written == 0:
        stored_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    document = Document(
        kb_id=kb_id,
        title=Path(original_name).stem,
        file_name=original_name,
        file_path=str(stored_path),
        file_type=suffix.lstrip("."),
        status="processing",
    )
    db.add(document)
    try:
        db.commit()
    except Exception:
        db.rollback()
        stored_path.unlink(missing_ok=True)
        raise
    db.refresh(document)

    document_chunks: list[DocumentChunk] = []
    try:
        logger.info("Processing document id=%s name=%s", document.id, original_name)
        parsed_text = await run_in_threadpool(parse_document_text, stored_path)
        if not parsed_text.strip():
            raise ValueError("No readable text was extracted from the document.")
        chunks = await run_in_threadpool(split_text, parsed_text)
        for chunk_index, chunk_content in enumerate(chunks):
            document_chunk = DocumentChunk(
                kb_id=kb_id,
                document_id=document.id,
                chunk_index=chunk_index,
                content=chunk_content,
                token_count=estimate_token_count(chunk_content),
            )
            db.add(document_chunk)
            document_chunks.append(document_chunk)

        db.flush()
        await run_in_threadpool(vector_store_service.add_chunks, document_chunks)

        document.status = "finished"
        document.content_length = len(parsed_text)
        document.content_preview = parsed_text[:500]
        document.error_message = ""
        db.commit()
    except Exception as exc:
        logger.exception("Document processing failed id=%s name=%s", document.id, original_name)
        db.rollback()
        chunk_ids = [chunk.id for chunk in document_chunks if chunk.id is not None]
        try:
            await run_in_threadpool(vector_store_service.delete_chunks, chunk_ids)
        except Exception:
            logger.exception("Vector compensation failed for document id=%s", document.id)
        db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).delete()
        document = db.get(Document, document.id)
        document.status = "failed"
        document.error_message = str(exc)[:1_000]
        db.commit()

    db.refresh(document)
    return _document_read(db, document)


@router.get("/api/kbs/{kb_id}/documents", response_model=list[DocumentRead])
def list_documents(
    kb_id: int,
    db: Session = Depends(get_db),
) -> list[DocumentRead]:
    knowledge_base = db.get(KnowledgeBase, kb_id)
    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found.",
        )

    rows = db.execute(
        select(Document, func.count(DocumentChunk.id))
        .outerjoin(DocumentChunk, DocumentChunk.document_id == Document.id)
        .where(Document.kb_id == kb_id)
        .group_by(Document.id)
        .order_by(Document.id.desc())
    )
    return [
        _document_read(db, document, chunk_count=int(chunk_count)) for document, chunk_count in rows
    ]


@router.get("/api/documents/{document_id}", response_model=DocumentRead)
def get_document(
    document_id: int,
    db: Session = Depends(get_db),
) -> DocumentRead:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )
    return _document_read(db, document)


@router.delete("/api/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
) -> None:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    chunk_ids = list(
        db.scalars(select(DocumentChunk.id).where(DocumentChunk.document_id == document_id))
    )
    db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).delete()
    file_path = Path(document.file_path)
    db.delete(document)
    db.commit()

    try:
        vector_store_service.delete_chunks(chunk_ids)
    except Exception:
        logger.exception("Vector cleanup failed for deleted document id=%s", document_id)
    _safe_unlink(file_path)


@router.get(
    "/api/documents/{document_id}/chunks",
    response_model=list[DocumentChunkRead],
)
def list_document_chunks(
    document_id: int,
    db: Session = Depends(get_db),
) -> list[DocumentChunk]:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )

    return list(
        db.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index.asc())
        )
    )


def _document_read(
    db: Session,
    document: Document,
    chunk_count: int | None = None,
) -> DocumentRead:
    if chunk_count is None:
        chunk_count = (
            db.scalar(
                select(func.count(DocumentChunk.id)).where(DocumentChunk.document_id == document.id)
            )
            or 0
        )
    return DocumentRead.model_validate({**document.__dict__, "chunk_count": int(chunk_count)})


def _safe_unlink(file_path: Path) -> None:
    try:
        file_path.resolve().relative_to(UPLOAD_DIR.resolve())
    except ValueError:
        logger.error("Refusing to delete path outside upload directory: %s", file_path)
        return
    try:
        file_path.unlink(missing_ok=True)
    except OSError:
        logger.exception("Could not delete uploaded file: %s", file_path)
