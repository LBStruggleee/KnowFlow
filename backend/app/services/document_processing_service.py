import logging
from pathlib import Path

from app.core.database import SessionLocal
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services.document_parser import parse_document_text
from app.services.text_chunker import estimate_token_count, split_text
from app.services.vector_store_service import vector_store_service
from sqlalchemy import select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def process_document(document_id: int) -> None:
    """Process one persisted document in a background worker thread."""
    with SessionLocal() as db:
        process_document_record(db, document_id)


def process_document_record(db: Session, document_id: int) -> None:
    """Parse and index a processing document using the supplied DB session."""
    document = db.get(Document, document_id)
    if document is None:
        logger.info("Skipping missing document id=%s", document_id)
        return
    if document.status != "processing":
        logger.info(
            "Skipping document id=%s because status=%s",
            document_id,
            document.status,
        )
        return

    document_chunks: list[DocumentChunk] = []
    try:
        logger.info("Processing document id=%s name=%s", document.id, document.file_name)
        parsed_text = parse_document_text(Path(document.file_path))
        if not parsed_text.strip():
            raise ValueError("No readable text was extracted from the document.")

        chunks = split_text(parsed_text)
        for chunk_index, chunk_content in enumerate(chunks):
            document_chunk = DocumentChunk(
                kb_id=document.kb_id,
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
        db.commit()
        logger.info("Document processing finished id=%s chunks=%s", document.id, len(chunks))
    except Exception as exc:
        logger.exception("Document processing failed id=%s", document_id)
        db.rollback()
        chunk_ids = [chunk.id for chunk in document_chunks if chunk.id is not None]
        try:
            vector_store_service.delete_chunks(chunk_ids)
        except Exception:
            logger.exception("Vector compensation failed for document id=%s", document_id)

        db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).delete()
        document = db.get(Document, document_id)
        if document is None:
            db.rollback()
            logger.info("Document id=%s was deleted while it was processing", document_id)
            return
        document.status = "failed"
        document.error_message = str(exc)[:1_000]
        db.commit()


def reset_document_for_retry(db: Session, document: Document) -> None:
    """Clear stale index state and put a failed document back in the queue."""
    chunk_ids = list(
        db.scalars(select(DocumentChunk.id).where(DocumentChunk.document_id == document.id))
    )
    try:
        vector_store_service.delete_chunks(chunk_ids)
    except Exception:
        logger.exception("Could not clear stale vectors before retry id=%s", document.id)
        raise

    db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).delete()
    document.status = "processing"
    document.content_length = 0
    document.content_preview = ""
    document.error_message = ""
    db.commit()
