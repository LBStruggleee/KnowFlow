import logging
from typing import Any

from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services.vector_store_service import parse_chunk_vector_id, vector_store_service
from sqlalchemy import select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

ORPHAN_SCAN_BATCH_SIZE = 500
ORPHAN_DELETE_BATCH_SIZE = 1000


def recover_interrupted_documents(db: Session) -> int:
    documents = db.query(Document).filter(Document.status == "processing").all()
    for document in documents:
        document.status = "failed"
        document.error_message = "处理任务因应用中断而停止，请点击重试。"
    if documents:
        db.commit()
    return len(documents)


def reconcile_orphan_vectors(db: Session) -> int:
    """Delete vectors whose chunks no longer exist in SQLite.

    Chroma deletions can fail while the SQLite row is already gone (see the
    delete endpoints), leaving vectors that keep participating in retrieval.
    This reconciliation compares every known collection against the SQLite
    chunk inventory. It is best effort: collections are handled one at a time
    and a failing collection only logs, so startup is never blocked.
    """
    try:
        valid_chunk_ids = set(db.scalars(select(DocumentChunk.id)))
    except Exception:
        logger.exception("Skipping orphan vector reconciliation; could not read chunk ids")
        return 0

    removed = 0
    for collection in vector_store_service.known_collections():
        try:
            removed += _delete_orphans(collection, valid_chunk_ids)
        except Exception:
            logger.exception("Orphan vector cleanup failed for collection %s", collection.name)
    if removed:
        logger.warning("Removed %s orphan vector(s) at startup", removed)
    return removed


def _delete_orphans(collection: Any, valid_chunk_ids: set[int]) -> int:
    orphans: list[str] = []
    offset = 0
    while True:
        batch = collection.get(include=[], limit=ORPHAN_SCAN_BATCH_SIZE, offset=offset)
        vector_ids = list(batch.get("ids", []))
        if not vector_ids:
            break
        for vector_id in vector_ids:
            chunk_id = parse_chunk_vector_id(vector_id)
            if chunk_id is None or chunk_id not in valid_chunk_ids:
                orphans.append(vector_id)
        if len(vector_ids) < ORPHAN_SCAN_BATCH_SIZE:
            break
        offset += len(vector_ids)
    if not orphans:
        return 0
    for start in range(0, len(orphans), ORPHAN_DELETE_BATCH_SIZE):
        collection.delete(ids=orphans[start : start + ORPHAN_DELETE_BATCH_SIZE])
    logger.info("Deleted %s orphan vector(s) from collection %s", len(orphans), collection.name)
    return len(orphans)
