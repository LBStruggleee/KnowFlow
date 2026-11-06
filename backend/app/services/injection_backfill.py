"""One-time backfill of injection flags for chunks that predate the guard.

Kept separate from the pure rule module so the guard stays importable without
SQLAlchemy, and separate from the processing service so the migration runner can
use it without pulling in the vector store.
"""

import logging

from app.models.document_chunk import DocumentChunk
from app.services.injection_guard import rules_as_text, scan_text
from sqlalchemy import select
from sqlalchemy.orm import Session

BACKFILL_BATCH_SIZE = 500
logger = logging.getLogger(__name__)


def backfill_injection_flags(db: Session, batch_size: int = BACKFILL_BATCH_SIZE) -> int:
    """Scan every chunk once and persist flag + matched rule names."""
    total = 0
    last_id = 0
    while True:
        chunks = list(
            db.scalars(
                select(DocumentChunk)
                .where(DocumentChunk.id > last_id)
                .order_by(DocumentChunk.id)
                .limit(batch_size)
            )
        )
        if not chunks:
            break
        for chunk in chunks:
            scan = scan_text(chunk.content)
            chunk.injection_flag = scan.flagged
            chunk.injection_rules = rules_as_text(scan.rules)
        db.commit()
        total += len(chunks)
        last_id = chunks[-1].id
    if total:
        logger.info("Backfilled injection flags for %s chunks", total)
    return total
