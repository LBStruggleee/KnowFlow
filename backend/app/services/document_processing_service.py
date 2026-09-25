import logging
from pathlib import Path

from app.core.database import SessionLocal
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.document_section import DocumentSection
from app.services.document_parser import ParsedDocument, parse_document_structure
from app.services.lexical_search import _build_search_text
from app.services.text_chunker import estimate_token_count, split_text_structured
from app.services.vector_store_service import vector_store_service
from sqlalchemy import select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def process_document(document_id: int) -> None:
    """Process one persisted document in a background worker thread."""
    with SessionLocal() as db:
        process_document_record(db, document_id)


def clear_document_sections(db: Session, document_id: int) -> None:
    """Delete all section rows of one document. Idempotent."""
    db.query(DocumentSection).filter(DocumentSection.document_id == document_id).delete()


def _persist_section_tree(
    db: Session,
    document: Document,
    root_title: str,
    parsed: ParsedDocument,
) -> dict[int, DocumentSection]:
    by_order: dict[int, DocumentSection] = {}
    root = DocumentSection(
        document_id=document.id,
        parent_section_id=None,
        title=root_title,
        section_path=root_title,
        section_level=0,
        section_order=0,
        chunk_count=0,
        summary="",
    )
    db.add(root)
    db.flush()
    by_order[-1] = root
    order_counter = 1
    for section in parsed.sections:
        if section.parent_order is None:
            parent = root
        else:
            parent = by_order.get(section.parent_order, root)
        node = DocumentSection(
            document_id=document.id,
            parent_section_id=parent.id,
            title=section.title,
            section_path=f"{parent.section_path} / {section.title}",
            section_level=section.level,
            section_order=order_counter,
            chunk_count=0,
            summary="",
        )
        db.add(node)
        db.flush()
        by_order[section.order] = node
        order_counter += 1
    return by_order


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
        parsed = parse_document_structure(Path(document.file_path))
        if not parsed.sections and not parsed.lead_content.strip():
            raise ValueError("No readable text was extracted from the document.")

        root_title = document.title or Path(document.file_path).stem
        owners = _persist_section_tree(db, document, root_title, parsed)
        chunk_owners: list[tuple[DocumentChunk, DocumentSection]] = []
        chunk_index = 0
        for result in split_text_structured(parsed.sections, root_content=parsed.lead_content):
            owner = owners.get(result.section_order, owners[-1])
            document_chunk = DocumentChunk(
                kb_id=document.kb_id,
                document_id=document.id,
                chunk_index=chunk_index,
                content=result.content,
                token_count=estimate_token_count(result.content),
                section_id=owner.id,
                search_text=_build_search_text(result.content, owner.section_path),
            )
            db.add(document_chunk)
            document_chunks.append(document_chunk)
            chunk_owners.append((document_chunk, owner))
            owner.chunk_count += 1
            chunk_index += 1

        db.flush()
        section_paths = {chunk.id: owner.section_path for chunk, owner in chunk_owners}
        vector_store_service.add_chunks(document_chunks, section_paths)

        document.status = "finished"
        document.content_length = sum(len(chunk.content) for chunk in document_chunks)
        document.content_preview = document_chunks[0].content[:500] if document_chunks else ""
        document.error_message = ""
        db.commit()
        logger.info(
            "Document processing finished id=%s chunks=%s", document.id, len(document_chunks)
        )
    except Exception as exc:
        logger.exception("Document processing failed id=%s", document_id)
        chunk_ids = [chunk.id for chunk in document_chunks if chunk.id is not None]
        db.rollback()
        try:
            vector_store_service.delete_chunks(chunk_ids)
        except Exception:
            logger.exception("Vector compensation failed for document id=%s", document_id)

        db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).delete()
        clear_document_sections(db, document_id)
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
    clear_document_sections(db, document.id)
    document.status = "processing"
    document.content_length = 0
    document.content_preview = ""
    document.error_message = ""
    db.commit()
