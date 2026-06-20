from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import BASE_DIR, get_db
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.knowledge_base import KnowledgeBase
from app.schemas.document_chunk import DocumentChunkRead
from app.schemas.document import DocumentRead
from app.services.document_parser import SUPPORTED_FILE_TYPES, parse_document_text
from app.services.text_chunker import estimate_token_count, split_text
from app.services.vector_store_service import vector_store_service

router = APIRouter(tags=["documents"])

UPLOAD_DIR = BASE_DIR / "storage" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.post(
    "/api/kbs/{kb_id}/documents/upload",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    kb_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> Document:
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

    content = await file.read()
    stored_path.write_bytes(content)

    document = Document(
        kb_id=kb_id,
        title=Path(original_name).stem,
        file_name=original_name,
        file_path=str(stored_path),
        file_type=suffix.lstrip("."),
        status="processing",
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    try:
        parsed_text = parse_document_text(stored_path)
        chunks = split_text(parsed_text)
        document_chunks: list[DocumentChunk] = []
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
        vector_store_service.add_chunks(document_chunks)

        document.status = "finished"
        document.content_length = len(parsed_text)
        document.content_preview = parsed_text[:500]
        document.error_message = ""
    except Exception as exc:
        document.status = "failed"
        document.error_message = str(exc)

    db.commit()
    db.refresh(document)
    return document


@router.get("/api/kbs/{kb_id}/documents", response_model=list[DocumentRead])
def list_documents(
    kb_id: int,
    db: Session = Depends(get_db),
) -> list[Document]:
    knowledge_base = db.get(KnowledgeBase, kb_id)
    if knowledge_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found.",
        )

    return list(
        db.scalars(
            select(Document)
            .where(Document.kb_id == kb_id)
            .order_by(Document.id.desc())
        )
    )


@router.get("/api/documents/{document_id}", response_model=DocumentRead)
def get_document(
    document_id: int,
    db: Session = Depends(get_db),
) -> Document:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found.",
        )
    return document


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
        db.scalars(
            select(DocumentChunk.id).where(DocumentChunk.document_id == document_id)
        )
    )
    vector_store_service.delete_chunks(chunk_ids)
    db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).delete()

    file_path = Path(document.file_path)
    if file_path.exists():
        file_path.unlink()

    db.delete(document)
    db.commit()


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
